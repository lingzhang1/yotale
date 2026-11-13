import Foundation
import SwiftData

// PendingOperationRecovery — P0 Phase 2/3 driver.
//
// On app foreground (scenePhase == .active) or Story reopen, find unfinished AI operations (PendingOperationModel
// rows that are not saved/abandoned) and RESUME them so a completed backend plan is never silently lost because
// the app was backgrounded, suspended, or force-quit. This mirrors AssetUnderstandingQueue.recoverOrphans +
// drain: it is non-blocking, opportunistic, and idempotent.
//
// CRITICAL GUARANTEES (owner mandate):
//   - NEVER submits a second model request. Resume reuses the persisted operationId + jobId and only
//     polls/fetches/renders (the coordinator's resumePendingOperation enforces this).
//   - NOT an indefinitely-running loop and NOT reliant on background URLSession / beginBackgroundTask. It runs
//     ONE pass when the app becomes active; active polling stops when the app is suspended (the poll Task is
//     suspended with the app) and a fresh pass resumes it on the next .active.
//   - Single-flight: an in-progress recovery set prevents repeated foreground/reopen events from creating
//     duplicate polling or rendering tasks for the same Story.
@MainActor
final class PendingOperationRecovery {
    private let context: ModelContext
    /// R1 — the account whose pending operations may be recovered in THIS pass. A resumable Story owned by a
    /// DIFFERENT account is skipped, so account B never resumes account A's generation (owner Phase 4.1/4.2).
    /// nil = signed out: recover nothing (there is no authenticated account to own the resumed render, and the
    /// paid resume path must not run unauthenticated).
    private let activeAccountId: String?

    // In-flight guard shared across recovery passes in this process: a Story whose resume is running is not
    // resumed again by a second foreground event. Coordinators are retained for the lifetime of their resume.
    private static var inFlight: Set<UUID> = []
    private static var retained: [UUID: StoryCreationCoordinator] = [:]

    init(context: ModelContext, activeAccountId: String? = nil) {
        self.context = context
        self.activeAccountId = activeAccountId
    }

    /// Fetch Stories that have a recoverable pending operation, resume each once — but ONLY those owned by the
    /// active account (R1 isolation).
    func recoverAll() {
        guard activeAccountId != nil else { return }   // signed out → recover nothing
        let desc = FetchDescriptor<PendingOperationModel>(sortBy: [SortDescriptor(\.updatedAt, order: .reverse)])
        let all = (try? context.fetch(desc)) ?? []
        // A pre-submit attempt past its resume window is discarded (resuming would start paid AI by surprise).
        // Split BEFORE deleting: never read a SwiftData object after it was deleted.
        let expired = all.filter { StoryCreationCoordinator.isPreparing($0) && !StoryCreationCoordinator.isResumable($0) }
        let rows = all.filter { StoryCreationCoordinator.isResumable($0) }
        if !expired.isEmpty {
            for row in expired { context.delete(row) }
            try? context.save()
        }
        guard !rows.isEmpty else { return }
        // One resume per Story (dedupe multiple rows defensively).
        var seen = Set<UUID>()
        for row in rows where !seen.contains(row.storyId) {
            seen.insert(row.storyId)
            resume(storyId: row.storyId)
        }
    }

    /// Resume the recoverable operation for one Story. Safe to call repeatedly — the in-flight guard makes a
    /// second call a no-op until the first resume finishes. Refuses a Story not owned by the active account.
    func resume(storyId: UUID) {
        guard !Self.inFlight.contains(storyId) else { return }
        let storyDesc = FetchDescriptor<StoryModel>(predicate: #Predicate { $0.id == storyId })
        guard let story = (try? context.fetch(storyDesc))?.first else { return }

        // R1 ownership guard: never resume another account's Story. A nil-owner Story (pre-R1, pre-backfill) is
        // also skipped rather than resumed under an arbitrary account.
        guard let active = activeAccountId, story.ownerAccountId == active else {
            MediaEngineV1.beacon("editplan-recover: SKIP story=\(storyId.uuidString.prefix(8)) — not owned by active account")
            return
        }

        let coord = StoryCreationCoordinator(planner: EditPlannerService(), context: context)
        guard coord.hasRecoverablePendingOperation(storyId: storyId) else { return }

        Self.inFlight.insert(storyId)
        Self.retained[storyId] = coord
        MediaEngineV1.beacon("editplan-recover: foreground pass resuming story=\(storyId.uuidString.prefix(8))")

        Task { @MainActor in
            defer { Self.inFlight.remove(storyId); Self.retained[storyId] = nil }
            // Re-resolve the operation's soundtrack (same path as Revise/Change Music) so a resumed render keeps
            // its music WHERE FEASIBLE; nil renders no-music rather than block the recovery of the video.
            let music = await Self.resolveMusicForResume(storyId: storyId, story: story, context: context)
            guard coord.resumePendingOperation(for: story, music: music) else { return }
            while coord.isCreating { try? await Task.sleep(nanoseconds: 300_000_000) }
            MediaEngineV1.beacon("editplan-recover: resume finished story=\(storyId.uuidString.prefix(8)) "
                + "state=\(String(describing: coord.state))")
        }
    }

    /// Re-resolve the pending op's soundtrack from its persisted musicSelectionRef
    /// ("mymusic:<id>" | "provider:<trackId>" | nil) WITHOUT a fresh MusicPlan. The plan was already planned
    /// music-aware; recovery only needs the soundtrack file + decoded analysis + the two mixing knobs, which we
    /// persisted at plan_ready. A provider track resolves via the TRACK-SCOPED analysisBoth + downloadSoundtrack
    /// (no recommend()/MusicPlan). My Music resolves locally. nil => no music (never blocks recovery). This is
    /// what keeps `original` recovery from unnecessarily rerunning MusicPlan.
    static func resolveMusicForResume(storyId: UUID, story: StoryModel, context: ModelContext) async
        -> StoryCreationCoordinator.MusicSelection? {
        let desc = FetchDescriptor<PendingOperationModel>(predicate: #Predicate { $0.storyId == storyId })
        guard let row = ((try? context.fetch(desc)) ?? []).first(where: { $0.isRecoverable }),
              let ref = row.musicSelectionRef, ref != "none" else { return nil }
        if ref.hasPrefix("mymusic:") {
            let assetId = String(ref.dropFirst("mymusic:".count))
            return CreateStoryPreviewView.myMusicSelection(assetId: assetId, story: story, context: context)
        }
        guard ref.hasPrefix("provider:") else { return nil }
        let trackId = String(ref.dropFirst("provider:".count))
        let candidates = MusicCandidatesService()
        // Track-scoped analysis + audio — NO MusicPlan recommend() call.
        guard let both = try? await candidates.analysisBoth(trackId: trackId),
              let url = try? await candidates.downloadSoundtrack(trackId: trackId) else {
            MediaEngineV1.beacon("editplan-recover: provider music re-resolve FAILED track=\(trackId.prefix(8)) -> no-music")
            return nil
        }
        return StoryCreationCoordinator.MusicSelection(
            // A post-submit resume never re-plans, so an empty plan was always enough there. A PRE-submit resume
            // (killed during preparation) still has to plan music-aware: use the attempt's stored MusicPlan.
            musicPlanJSON: StoryCreationCoordinator.decodeStoredJSON(row.musicPlanJSON) ?? .object([:]),
            trackId: trackId,
            analysisJSON: both.raw,
            analysis: both.analysis,
            soundtrackURL: url,
            soundtrackRole: row.soundtrackRole ?? "supportive",
            nativeAudioPriority: row.nativeAudioPriority ?? "selective",
            trackTitle: "Soundtrack")
    }
}

// MARK: - Lost-reply recovery: the exact submit bytes, kept on device until the job id is known

/// The prepared multipart body of a job submit whose reply has not arrived yet, keyed by operation_id. Written
/// BEFORE the POST and deleted as soon as the job id is known (or the operation ends). If the app is suspended or
/// killed while the reply is in flight, a later resume re-sends these exact bytes: the server matches the
/// operation_id + payload fingerprint and returns the SAME job — never a second inference, never a 409. Local
/// only (Caches; it holds the same contact sheets the planner receives) and short-lived.
enum PendingJobSubmitStore {
    private static var dir: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("pending-edit-plan-submits", isDirectory: true)
    }
    private static func safe(_ operationId: String) -> String {
        String(operationId.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0 == "-" }
            .map(Character.init))
    }
    private static func bodyURL(_ operationId: String) -> URL { dir.appendingPathComponent("\(safe(operationId)).body") }
    private static func boundaryURL(_ operationId: String) -> URL { dir.appendingPathComponent("\(safe(operationId)).boundary") }

    static func save(_ prepared: PreparedJobSubmit, operationId: String) {
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? prepared.body.write(to: bodyURL(operationId), options: .atomic)
        try? Data(prepared.boundary.utf8).write(to: boundaryURL(operationId), options: .atomic)
    }

    static func load(operationId: String) -> PreparedJobSubmit? {
        guard let body = try? Data(contentsOf: bodyURL(operationId)),
              let b = try? Data(contentsOf: boundaryURL(operationId)),
              let boundary = String(data: b, encoding: .utf8), !body.isEmpty, !boundary.isEmpty else { return nil }
        return PreparedJobSubmit(body: body, boundary: boundary)
    }

    static func exists(operationId: String) -> Bool {
        FileManager.default.fileExists(atPath: bodyURL(operationId).path)
    }

    static func remove(operationId: String) {
        try? FileManager.default.removeItem(at: bodyURL(operationId))
        try? FileManager.default.removeItem(at: boundaryURL(operationId))
    }
}
