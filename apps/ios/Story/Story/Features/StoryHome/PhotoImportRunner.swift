import Foundation
import SwiftUI
import PhotosUI
import AVFoundation
import BackgroundTasks
import CoreTransferable
import UniformTypeIdentifiers
import UIKit
import os

// PhotoImportRunner — the ONE owner of a running "copy picked videos out of Photos" import.
//
// Why it exists: the copy used to run in a Task started by the picker's view modifier, with only a ~30 s
// `beginBackgroundTask`. Leaving the app or locking the phone suspended it, so a 38-video import paused as soon
// as the user stopped watching it. This runner is app-scoped (not tied to any view) and, on iOS 26+, asks the
// system for a user-initiated BGContinuedProcessingTask that keeps the copy running with the app in the
// background or the phone locked, showing real progress in the system UI.
//
//  - Moments are still handed to the caller every `flushEvery` copied files, so whatever has been copied is
//    durable even if the system ends the task or the app is killed.
//  - Progress is real: items finished plus the system's own per-item load progress (iCloud download/copy).
//    Nothing is extrapolated. A stalled item stops the progress, and the system may then expire the task.
//  - Expiry never drops work: the loop is simply suspended with the app and continues on the next foreground.
//    Only a kill loses the not-yet-copied items (PhotosPickerItem cannot be persisted without full library
//    access), and those can be picked again.
//  - Below iOS 26, or when the system refuses the request, it degrades to beginBackgroundTask + screen awake.
@MainActor
final class PhotoImportRunner {
    static let shared = PhotoImportRunner()

    /// Must match Info.plist `BGTaskSchedulerPermittedIdentifiers` ($(PRODUCT_BUNDLE_IDENTIFIER).photo.import).
    static var identifier: String { (Bundle.main.bundleIdentifier ?? "app.yotale") + ".photo.import" }
    /// Hand Moments to the caller after every N copied files.
    static let flushEvery = 3

    private struct Job {
        let items: [PhotosPickerItem]
        let onPicked: ([ImportedMedia]) -> Void
        let onProgress: (ImportProgress) -> Void
    }

    private var jobs: [Job] = []
    private(set) var isRunning = false
    /// Items finished (copied or failed) across all jobs in this run, and the run's total, for system progress.
    private var runFinished = 0
    private var runTotal = 0
    private let itemProgress = ProgressHolder()
    private var legacyTask: UIBackgroundTaskIdentifier = .invalid
    private var registered = false
    private var systemTaskBox: AnyObject?
    private static let awakeKey = "photo-import"
    nonisolated private static let log = Logger(subsystem: "app.yotale", category: "photo-import")

    /// Start (or append to) an import. Returns immediately; work runs until every queued item is handled.
    func enqueue(_ items: [PhotosPickerItem],
                 onPicked: @escaping ([ImportedMedia]) -> Void,
                 onProgress: @escaping (ImportProgress) -> Void) {
        guard !items.isEmpty else { return }
        jobs.append(Job(items: items, onPicked: onPicked, onProgress: onProgress))
        runTotal += items.count
        Self.log.info("import enqueued \(items.count, privacy: .public) items, run total \(self.runTotal, privacy: .public)")
        guard !isRunning else { return }   // the running loop picks the new job up
        isRunning = true
        ScreenAwake.shared.hold(Self.awakeKey)
        if legacyTask == .invalid {
            legacyTask = UIApplication.shared.beginBackgroundTask(withName: "photo-import") { [weak self] in
                MainActor.assumeIsolated { self?.endLegacyTask() }
            }
        }
        if #available(iOS 26.0, *) { submitSystemTask() }
        Task { await runLoop() }
    }

    private func runLoop() async {
        while !jobs.isEmpty {
            let job = jobs.removeFirst()
            await run(job)
        }
        isRunning = false
        runFinished = 0
        runTotal = 0
        ScreenAwake.shared.release(Self.awakeKey)
        endLegacyTask()
        if #available(iOS 26.0, *) { finishSystemTask(success: true) }
    }

    private func run(_ job: Job) async {
        let total = job.items.count
        job.onProgress(ImportProgress(total: total, done: 0, failed: 0, finished: false, phase: .preparing))
        var pending: [ImportedMedia] = []
        var copied = 0
        var failed = 0
        for (index, item) in job.items.enumerated() {
            do {
                pending.append(try await copy(item))
                copied += 1
                Self.log.info("import item \(index + 1, privacy: .public)/\(total, privacy: .public) ok app=\(Self.appState(), privacy: .public)")
            } catch {
                failed += 1
                Self.log.error("import item \(index + 1, privacy: .public)/\(total, privacy: .public) failed app=\(Self.appState(), privacy: .public): \(String(describing: error), privacy: .public)")
            }
            itemProgress.set(nil)
            runFinished += 1
            if pending.count >= Self.flushEvery {
                job.onPicked(pending)
                pending = []
            }
            job.onProgress(ImportProgress(total: total, done: copied, failed: failed, finished: false, phase: .importing))
        }
        if !pending.isEmpty { job.onPicked(pending) }
        job.onProgress(ImportProgress(total: total, done: copied, failed: failed, finished: true, phase: .importing))
    }

    /// Copy one picked video into MediaStore. The file is streamed to disk by the system (never held as Data).
    private func copy(_ item: PhotosPickerItem) async throws -> ImportedMedia {
        let holder = itemProgress
        let movie: PickedMovie = try await withCheckedThrowingContinuation { cont in
            let p = item.loadTransferable(type: PickedMovie.self) { result in
                switch result {
                case .success(let m?): cont.resume(returning: m)
                case .success(nil): cont.resume(throwing: CocoaError(.fileReadUnknown))
                case .failure(let e): cont.resume(throwing: e)
                }
            }
            holder.set(p)
        }
        do {
            let avAsset = AVURLAsset(url: movie.url)
            let dur = CMTimeGetSeconds(avAsset.duration)
            // Safeguard 5: recover the ORIGINAL capture date + location from the file's OWN embedded metadata
            // (no Photos read-auth / asset-id dependency). nil when absent ("unknown").
            let meta = await ImportedMediaMetadata.recover(from: avAsset)
            let rel = try MediaStore.shared.adoptCapturedFile(tempURL: movie.url)
            return ImportedMedia(path: rel, duration: dur.isFinite ? dur : 0, capturedAt: meta.capturedAt,
                                 latitude: meta.latitude, longitude: meta.longitude)
        } catch {
            try? FileManager.default.removeItem(at: movie.url)
            throw error
        }
    }

    private func endLegacyTask() {
        guard legacyTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(legacyTask)
        legacyTask = .invalid
    }

    private static func appState() -> String {
        switch UIApplication.shared.applicationState {
        case .active: return "active"
        case .inactive: return "inactive"
        case .background: return "background"
        @unknown default: return "unknown"
        }
    }

    /// Run progress in [0, 1]: finished items plus the in-flight item's own load fraction.
    private var runFraction: Double {
        guard runTotal > 0 else { return 0 }
        let partial = min(max(itemProgress.get()?.fractionCompleted ?? 0, 0), 1)
        return min(1, (Double(runFinished) + partial) / Double(runTotal))
    }

    // MARK: - iOS 26 continued processing

    @available(iOS 26.0, *)
    private func submitSystemTask() {
        if !registered {
            // Dynamic registration immediately before submit is the documented pattern for continued tasks.
            let ok = BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.identifier, using: nil) { task in
                guard let task = task as? BGContinuedProcessingTask else {
                    task.setTaskCompleted(success: false)
                    return
                }
                let box = ImportTaskBox(task)
                Task { @MainActor in PhotoImportRunner.shared.supervise(box) }
            }
            guard ok else { Self.log.error("photo-import bgtask register failed"); return }
            registered = true
        }
        let request = BGContinuedProcessingTaskRequest(
            identifier: Self.identifier,
            title: L10n.t("Importing your videos"),
            subtitle: L10n.t("\(runTotal) videos"))
        // Start now or not at all: the user just tapped Add and is watching. If refused, the foreground copy
        // (plus beginBackgroundTask) still runs.
        request.strategy = .fail
        do {
            try BGTaskScheduler.shared.submit(request)
            Self.log.info("photo-import bgtask submitted total=\(self.runTotal, privacy: .public)")
        } catch {
            Self.log.error("photo-import bgtask submit refused: \(String(describing: error), privacy: .public)")
        }
    }

    @available(iOS 26.0, *)
    private func supervise(_ box: ImportTaskBox) {
        let task = box.task
        guard isRunning else { task.setTaskCompleted(success: true); return }   // finished before launch
        systemTaskBox = box
        Self.log.info("photo-import bgtask started app=\(Self.appState(), privacy: .public)")
        task.expirationHandler = {
            // System expiry or the user cancelled from the system UI. The copy loop is NOT stopped: it is
            // suspended with the app and continues on the next foreground. Copied Moments are already saved.
            Task { @MainActor in
                Self.log.info("photo-import bgtask EXPIRED")
                PhotoImportRunner.shared.finishSystemTask(success: false)
            }
        }
        Task { @MainActor in
            let units: Int64 = 1000
            while let current = self.systemTaskBox as? ImportTaskBox, current === box, self.isRunning {
                task.progress.totalUnitCount = units
                task.progress.completedUnitCount = max(task.progress.completedUnitCount,
                                                       Int64(self.runFraction * Double(units)))
                task.updateTitle(L10n.t("Importing your videos"),
                                 subtitle: L10n.t("\(self.runFinished) of \(self.runTotal) done"))
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
    }

    @available(iOS 26.0, *)
    private func finishSystemTask(success: Bool) {
        guard let box = systemTaskBox as? ImportTaskBox else { return }
        systemTaskBox = nil
        if success { box.task.progress.completedUnitCount = box.task.progress.totalUnitCount }
        Self.log.info("photo-import bgtask completed success=\(success, privacy: .public)")
        box.task.setTaskCompleted(success: success)
    }
}

/// A picked video delivered as a FILE (streamed to disk by the system), never as an in-memory `Data`.
/// A long 4K clip can be hundreds of MB; holding it as `Data` risked a memory kill mid-import.
struct PickedMovie: Transferable {
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

/// The in-flight item's system load Progress, set from the transfer callback and read by the supervisor.
private final class ProgressHolder: @unchecked Sendable {
    private let lock = NSLock()
    private var progress: Progress?
    func set(_ p: Progress?) { lock.lock(); progress = p; lock.unlock() }
    func get() -> Progress? { lock.lock(); defer { lock.unlock() }; return progress }
}

/// BGTask is not Sendable; the supervisor hops straight onto the main actor, so a box is enough.
@available(iOS 26.0, *)
private final class ImportTaskBox: @unchecked Sendable {
    let task: BGContinuedProcessingTask
    init(_ t: BGContinuedProcessingTask) { task = t }
}
