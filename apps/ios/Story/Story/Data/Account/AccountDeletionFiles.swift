import Foundation

/// Durable on-device state for account deletion (design 5.7). Two files in `Library/AccountDeletion/`, which the
/// local wipe never removes (it clears Documents, Caches, tmp and Application Support only):
///
///   * `request.json`  a PENDING NETWORK REQUEST: the request id and receipt secret, written BEFORE the POST so a
///                     lost response, a 503 or an app kill can be resolved through the public status route. It
///                     never authorizes a wipe on its own.
///   * `wipe-intent`   the INSTRUCTION TO WIPE: written only after acceptance is established (202, 409, or the
///                     status route says accepted). Removed only after every wipe step succeeded.
///
/// Writes are atomic (temp file + rename) with `completeUntilFirstUserAuthentication` protection, so they are
/// readable at a cold start after the first unlock (including a background launch).
enum AccountDeletionFiles {
    struct PendingRequest: Codable, Equatable {
        enum Stage: String, Codable { case submitting, accepted }
        var requestId: String
        var receiptSecret: String
        var createdAt: Date
        var stage: Stage
        /// "SignInWithApple" / "Google" / nil (email). Kept so the completion screen can show the Apple step.
        var federatedProvider: String?
    }

    struct WipeIntent: Codable, Equatable {
        var requestId: String?      // nil when another device confirmed the deletion
        var createdAt: Date
    }

    static var directory: URL {
        FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AccountDeletion", isDirectory: true)
    }
    static var requestURL: URL { directory.appendingPathComponent("request.json") }
    static var wipeIntentURL: URL { directory.appendingPathComponent("wipe-intent") }

    // ---- request.json -------------------------------------------------------------------------------------
    static func pendingRequest() -> PendingRequest? { read(PendingRequest.self, at: requestURL) }

    static func savePendingRequest(_ r: PendingRequest) throws { try write(r, to: requestURL) }

    static func clearPendingRequest() { try? FileManager.default.removeItem(at: requestURL) }

    // ---- wipe-intent ---------------------------------------------------------------------------------------
    static func wipeIntent() -> WipeIntent? { read(WipeIntent.self, at: wipeIntentURL) }

    static func saveWipeIntent(_ w: WipeIntent) throws { try write(w, to: wipeIntentURL) }

    /// Called ONLY after every wipe step succeeded (LocalWipe).
    static func clearWipeIntent() throws {
        if FileManager.default.fileExists(atPath: wipeIntentURL.path) {
            try FileManager.default.removeItem(at: wipeIntentURL)
        }
    }

    // ---- helpers ------------------------------------------------------------------------------------------
    /// 32 random bytes as 64 lowercase hex characters (the receipt secret); the server stores only its SHA-256.
    static func newReceiptSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let rc = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        precondition(rc == errSecSuccess, "SecRandomCopyBytes failed")
        return bytes.map { String(format: "%02x", $0) }.joined()
    }

    private static func read<T: Decodable>(_ type: T.Type, at url: URL) -> T? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return try? dec.decode(T.self, from: data)
    }

    private static func write<T: Encodable>(_ value: T, to url: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let enc = JSONEncoder()
        enc.dateEncodingStrategy = .iso8601
        try enc.encode(value).write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}
