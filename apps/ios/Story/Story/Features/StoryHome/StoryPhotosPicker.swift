import SwiftUI
import PhotosUI
import AVFoundation
import CoreTransferable
import UniformTypeIdentifiers
import os

// StoryPhotosPicker — frozen Figma "+ Add photos or videos" (add-to-Moments
// path). Wraps PhotosPicker, copies each picked VIDEO into MediaStore, and hands
// back (relativePath, durationSeconds) for StoryUseCases.addExistingMedia.
// Local/mechanical only — NO AI analysis (the analyze path stays disabled;
// ui-capability-matrix). C3.5.
//
// R-c.1 UX: copying picked videos out of the Photos library (often an iCloud
// download of the full file) can take seconds with NO visible change on Story
// Home, which read as "my import failed". `onProgress` reports the copy as it
// happens — started (0 of N), each item done (k of N), and finished — so the
// caller can show an honest, non-blocking "Adding your videos…" signal.

/// Progress of a running import, driven from the picker. `done`/`total` count
/// COPIED items; `failed` counts items that couldn't be read/copied (reported at
/// the end so the user is never told "done" when some silently dropped).
struct ImportProgress: Equatable {
    /// Operation-specific phase for honest, non-percentage feedback (Phase 5).
    enum Phase: Equatable {
        case preparing     // selection received; about to read the first item
        case importing     // copying items out of Photos into MediaStore
        case analyzing     // files persisted; Asset Understanding enqueued/running
    }
    var total: Int
    var done: Int
    var failed: Int
    var finished: Bool
    var phase: Phase = .importing
    static let idle = ImportProgress(total: 0, done: 0, failed: 0, finished: true, phase: .importing)
}

/// Pure mapping from import progress to an honest one-line banner. Extracted so it's unit-testable without a
/// SwiftUI host. Never says "done" while work is in flight, surfaces partial failures plainly, and names the
/// current operation (Preparing / Importing / Analyzing) WITHOUT fabricating a progress percentage.
enum StoryImportCopy {
    static func line(for p: ImportProgress) -> String {
        if !p.finished {
            switch p.phase {
            case .preparing:
                return L10n.t("Preparing selected media…")
            case .importing:
                return p.total > 1 ? L10n.t("Importing… (\(p.done) of \(p.total))") : L10n.t("Importing your video…")
            case .analyzing:
                return L10n.t("Analyzing moments…")
            }
        }
        // Finished.
        if p.done == 0 { return L10n.t("Couldn't add those videos. Please try again.") }
        if p.failed > 0 {
            return L10n.t("Added \(p.done) · \(p.failed) couldn't be added.")
        }
        return p.done > 1 ? L10n.t("Added \(p.done) videos.") : L10n.t("Added your video.")
    }
}

/// One imported video + the ORIGINAL metadata recovered from its embedded container (Camera Metadata P0).
/// `capturedAt`/`latitude`/`longitude` are nil when the file carried none ("unknown", never fabricated).
struct ImportedMedia: Equatable {
    let path: String
    let duration: Double
    var capturedAt: Date? = nil
    var latitude: Double? = nil
    var longitude: Double? = nil
}

/// A picked video delivered as a FILE (streamed to disk by the system), never as an in-memory `Data`.
/// A long 4K clip can be hundreds of MB; holding it as `Data` risked a memory kill mid-import.
private struct PickedMovie: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { received in
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString + ".mov")
            try FileManager.default.copyItem(at: received.file, to: dest)
            return PickedMovie(url: dest)
        }
    }
}

private let importLog = Logger(subsystem: "app.yotale", category: "photo-import")

extension View {
    func photosPickerSheet(
        isPresented: Binding<Bool>,
        onProgress: @escaping (ImportProgress) -> Void = { _ in },
        onPicked: @escaping ([ImportedMedia]) -> Void
    ) -> some View {
        modifier(PhotosPickerModifier(isPresented: isPresented, onProgress: onProgress, onPicked: onPicked))
    }
}

private struct PhotosPickerModifier: ViewModifier {
    @Binding var isPresented: Bool
    let onProgress: (ImportProgress) -> Void
    let onPicked: ([ImportedMedia]) -> Void
    @State private var selection: [PhotosPickerItem] = []

    func body(content: Content) -> some View {
        content
            .photosPicker(isPresented: $isPresented, selection: $selection,
            // Per-session cap (you can reopen the picker to add more — each import APPENDS to the Story).
            // Raised to 100 so a large shoot can be imported in one pass.
                          maxSelectionCount: 100, matching: .videos)
            .onChange(of: selection) { _, items in
                guard !items.isEmpty else { return }
                Task { await importAll(items) }
            }
    }

    private func importAll(_ items: [PhotosPickerItem]) async {
        let total = items.count
        // Phase 5: a brief "Preparing selected media…" before the first copy begins.
        await report(ImportProgress(total: total, done: 0, failed: 0, finished: false, phase: .preparing))

        // Keep the screen on and ask iOS for extra time while copying. Neither survives a long suspension,
        // which is why Moments are persisted in chunks below instead of once at the end.
        let awakeKey = "photo-import.\(UUID().uuidString.prefix(8))"
        await MainActor.run { ScreenAwake.shared.hold(awakeKey) }
        let bgTask = await MainActor.run {
            UIApplication.shared.beginBackgroundTask(withName: "photo-import") {}
        }
        defer {
            Task { @MainActor in
                ScreenAwake.shared.release(awakeKey)
                if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask) }
            }
        }

        // Persist Moments every `flushEvery` copied files (and at the end), so an interruption keeps
        // everything already copied instead of orphaning it in storage with no Moment.
        let flushEvery = 3
        var pending: [ImportedMedia] = []
        var copied = 0
        var failed = 0
        for (index, item) in items.enumerated() {
            var tmp: URL?
            do {
                guard let movie = try await item.loadTransferable(type: PickedMovie.self) else {
                    throw CocoaError(.fileReadUnknown)
                }
                tmp = movie.url
                let avAsset = AVURLAsset(url: movie.url)
                let dur = CMTimeGetSeconds(avAsset.duration)
                // Safeguard 5: recover the ORIGINAL capture date + location from the file's OWN embedded
                // metadata (no Photos read-auth / asset-id dependency). nil when absent ("unknown").
                let meta = await ImportedMediaMetadata.recover(from: avAsset)
                let rel = try MediaStore.shared.adoptCapturedFile(tempURL: movie.url)
                tmp = nil
                pending.append(ImportedMedia(path: rel, duration: dur.isFinite ? dur : 0, capturedAt: meta.capturedAt, latitude: meta.latitude, longitude: meta.longitude))
                copied += 1
                importLog.info("import item \(index + 1, privacy: .public)/\(total, privacy: .public) ok")
            } catch {
                failed += 1
                if let tmp { try? FileManager.default.removeItem(at: tmp) }
                importLog.error("import item \(index + 1, privacy: .public)/\(total, privacy: .public) failed: \(String(describing: error), privacy: .public)")
            }
            if pending.count >= flushEvery {
                let batch = pending
                pending = []
                await MainActor.run { onPicked(batch) }
            }
            await report(ImportProgress(total: total, done: copied, failed: failed,
                                        finished: false, phase: .importing))
        }
        let rest = pending
        let finalCopied = copied
        let finalFailed = failed
        await MainActor.run {
            selection = []
            if !rest.isEmpty { onPicked(rest) }
            onProgress(ImportProgress(total: total, done: finalCopied, failed: finalFailed,
                                      finished: true, phase: .importing))
        }
    }

    private func report(_ p: ImportProgress) async {
        await MainActor.run { onProgress(p) }
    }
}
