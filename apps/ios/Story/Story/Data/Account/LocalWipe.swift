import Foundation

/// Local data removal after an accepted account deletion (design 5.7).
///
/// Lifecycle (chosen so no content created after acceptance can ever be erased):
///   1. Acceptance established -> `wipe-intent` written -> the app shows the deletion lock screen for the rest of
///      the process (no sign-in, capture, import or Story creation is reachable), signs out and stops cloud
///      writers (they need a token). Nothing is deleted in-session: the SwiftData store is open, and deleting rows
///      under the live upload/AU/render queues risks crashing on deleted models.
///   2. Next cold start, in `StoryApp.init` BEFORE any `ModelContainer` exists: `runIfPending()` deletes the
///      store files (default and recovery-fallback, with -shm/-wal), Documents, Caches, tmp, the rest of
///      Application Support, the Keychain session and the UserDefaults domain (the app language is restored).
///   3. Only when every step succeeded is `wipe-intent` removed; then the app opens a new, empty store. A
///      force-quit or failure at any step leaves the marker, and the next launch repeats the whole wipe (each step
///      is idempotent). New content is possible only after step 3, so it can never be wiped.
///
/// A file of an OPEN ModelContainer is never deleted: `runIfPending()` runs before the container is created, and
/// the in-app retry runs only while the app is on an in-memory container. The migration-failure path in
/// StoryApp still never deletes data; this marker-driven wipe is the only code that deletes a store file.
@MainActor
enum LocalWipe {
    enum Result: Equatable { case nothingPending, wiped, failed(String) }

    /// Store files of both containers the app can open (StoryApp: default.store, recovery-fallback.store).
    static let storeNames = ["default.store", "recovery-fallback.store"]
    static let storeSuffixes = ["", "-shm", "-wal"]

    @discardableResult
    static func runIfPending(fileManager fm: FileManager = .default, defaults: UserDefaults = .standard,
                             bundleId: String? = Bundle.main.bundleIdentifier,
                             clearKeychain: () -> Void = { KeychainStore.clear() }) -> Result {
        guard AccountDeletionFiles.wipeIntent() != nil else { return .nothingPending }
        do {
            try wipeEverything(fileManager: fm)
            clearKeychain()
            resetDefaults(defaults, bundleId: bundleId)
            try verifyEmpty(fileManager: fm)
            try AccountDeletionFiles.clearWipeIntent()          // LAST: only after every step succeeded
            return .wiped
        } catch {
            return .failed(String(describing: error).prefix(160).description)
        }
    }

    static func wipeEverything(fileManager fm: FileManager) throws {
        let appSupport = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        // Store files first and explicitly (both containers), then whole directories.
        for name in storeNames {
            for suffix in storeSuffixes {
                let url = appSupport.appendingPathComponent(name + suffix)
                if fm.fileExists(atPath: url.path) { try fm.removeItem(at: url) }
            }
        }
        for dir in directoriesToEmpty(fm) { try emptyDirectory(dir, fileManager: fm) }
    }

    static func directoriesToEmpty(_ fm: FileManager) -> [URL] {
        [fm.urls(for: .documentDirectory, in: .userDomainMask)[0],
         fm.urls(for: .cachesDirectory, in: .userDomainMask)[0],
         fm.temporaryDirectory,
         fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]]
    }

    /// Remove every child of `dir` (the directory itself stays; the system owns it).
    static func emptyDirectory(_ dir: URL, fileManager fm: FileManager) throws {
        guard fm.fileExists(atPath: dir.path) else { return }
        for child in try fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil, options: []) {
            try fm.removeItem(at: child)
        }
    }

    static func resetDefaults(_ defaults: UserDefaults, bundleId: String?) {
        let language = defaults.string(forKey: AppLanguageStore.defaultsKey)   // the only allow-listed key
        if let bundleId { defaults.removePersistentDomain(forName: bundleId) }
        if let language { defaults.set(language, forKey: AppLanguageStore.defaultsKey) }
    }

    private struct NotEmpty: Error, CustomStringConvertible {
        let path: String
        var description: String { "still present: \(path)" }
    }

    static func verifyEmpty(fileManager fm: FileManager) throws {
        let appSupport = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        for name in storeNames {
            for suffix in storeSuffixes where fm.fileExists(atPath: appSupport.appendingPathComponent(name + suffix).path) {
                throw NotEmpty(path: name + suffix)
            }
        }
        // Directory contents were removed child by child above, and any failure threw; the store files are the
        // one thing that must provably be gone before a new container opens.
    }
}
