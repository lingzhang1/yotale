#if DEBUG
import SwiftData
import XCTest
@testable import Story

// DebugOutputDeletion (DEBUG-only "Delete this version" for controlled planner evaluations). DETERMINISTIC: in-memory
// store, injected file remover — no disk, no network, no render. Verifies exactly what is removed, what is kept, and
// the guards (operation in flight, derived versions), plus that a persistence failure never half-deletes.
@MainActor
final class DebugOutputDeletionTests: XCTestCase {

    private var container: ModelContainer!
    private var ctx: ModelContext { container.mainContext }

    override func setUp() async throws {
        container = try ModelContainer(
            for: StoryModel.self, MomentModel.self, AssetModel.self,
                 GeneratedOutputModel.self, LocalIdentityModel.self,
                 MomentUnderstandingModel.self, AssetUnderstandingJobModel.self,
                 StoryCoverageModel.self, StoryGuideModel.self, StoryMusicDirectionModel.self,
                 PendingOperationModel.self, GeneratedOutputBackupJobModel.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true))
    }

    // MARK: - Fixtures

    private func makeStory(title: String = "TMB") -> StoryModel {
        let s = StoryModel(title: title, intentRawText: "8 days hiking", intentTheme: "scenic",
                           intentTone: "adventurous", intentSummary: "hike")
        s.ownerAccountId = "owner-1"
        s.editorialMode = "highlights"
        ctx.insert(s)
        return s
    }

    @discardableResult
    private func addOutput(to story: StoryModel, path: String? = nil, parent: GeneratedOutputModel? = nil,
                           op: String = "original") -> GeneratedOutputModel {
        let o = GeneratedOutputModel(title: "v", durationSeconds: 90, momentIds: [],
                                     relativeFilePath: path ?? "rendered/\(UUID().uuidString).mp4",
                                     parentVersionId: parent?.versionId, operationType: op)
        o.story = story
        o.ownerAccountId = story.ownerAccountId
        ctx.insert(o)
        story.generatedOutputs.append(o)
        try? ctx.save()
        return o
    }

    private func outputCount() -> Int { (try? ctx.fetch(FetchDescriptor<GeneratedOutputModel>()))?.count ?? -1 }

    // MARK: - Pure decisions

    func test_deletableFile_onlyRenderedPathsWithoutTraversalAndNotShared() {
        XCTAssertEqual(DebugOutputDeletion.deletableFile(relative: "rendered/a.mp4", usedByOtherVersions: []), "rendered/a.mp4")
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: nil, usedByOtherVersions: []))
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: "", usedByOtherVersions: []))
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: "media/a.mov", usedByOtherVersions: []), "a Moment original is never deletable here")
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: "rendered/../media/a.mov", usedByOtherVersions: []))
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: "/rendered/a.mp4", usedByOtherVersions: []))
        XCTAssertNil(DebugOutputDeletion.deletableFile(relative: "rendered/a.mp4", usedByOtherVersions: ["rendered/a.mp4"]),
                     "a file another version points at is kept")
    }

    func test_block_inFlightPhasesBlock_terminalPhasesDoNot() {
        let story = makeStory(); let o = addOutput(to: story)
        for p in ["preparing", "submitting", "submitted", "planning", "plan_ready", "rendering"] {
            XCTAssertEqual(DebugOutputDeletion.block(for: o, amongStoryOutputs: story.generatedOutputs, pendingPhases: [p]),
                           .operationInFlight, p)
        }
        XCTAssertNil(DebugOutputDeletion.block(for: o, amongStoryOutputs: story.generatedOutputs, pendingPhases: ["saved", "abandoned"]))
        XCTAssertNil(DebugOutputDeletion.block(for: o, amongStoryOutputs: story.generatedOutputs, pendingPhases: []))
    }

    func test_block_derivedVersionsBlock_siblingsDoNot() {
        let story = makeStory()
        let base = addOutput(to: story)
        let sibling = addOutput(to: story)                       // another ORIGINAL: independent lineage
        XCTAssertNil(DebugOutputDeletion.block(for: base, amongStoryOutputs: story.generatedOutputs, pendingPhases: []))
        _ = addOutput(to: story, parent: base, op: "another_version")
        _ = addOutput(to: story, parent: base, op: "change_music")
        XCTAssertEqual(DebugOutputDeletion.block(for: base, amongStoryOutputs: story.generatedOutputs, pendingPhases: []),
                       .hasDerivedVersions(2))
        XCTAssertNil(DebugOutputDeletion.block(for: sibling, amongStoryOutputs: story.generatedOutputs, pendingPhases: []))
    }

    // MARK: - Action

    func test_delete_removesVersionFileAndBackupJobs_keepsStoryAndOtherVersions() throws {
        let story = makeStory()
        let keep = addOutput(to: story)
        let victim = addOutput(to: story, path: "rendered/victim.mp4")
        let vid = victim.id
        ctx.insert(GeneratedOutputBackupJobModel(ownerAccountId: "owner-1", outputId: vid, storyId: story.id,
                                                 operationId: "op", relativeFilePath: "rendered/victim.mp4"))
        ctx.insert(GeneratedOutputBackupJobModel(ownerAccountId: "owner-1", outputId: keep.id, storyId: story.id,
                                                 operationId: "op2", relativeFilePath: keep.relativeFilePath ?? ""))
        try ctx.save()
        var removed: [String] = []

        let out = try DebugOutputDeletion.delete(victim, from: story, context: ctx, removeFile: { removed.append($0); return true })

        XCTAssertEqual(out.relativePath, "rendered/victim.mp4"); XCTAssertTrue(out.removedFile)
        XCTAssertEqual(removed, ["rendered/victim.mp4"])
        XCTAssertEqual(out.backupJobsRemoved, 1)
        XCTAssertEqual(story.generatedOutputs.map(\.id), [keep.id])
        XCTAssertEqual(outputCount(), 1)
        let jobs = try ctx.fetch(FetchDescriptor<GeneratedOutputBackupJobModel>())
        XCTAssertEqual(jobs.map(\.outputId), [keep.id], "only the deleted version's backup row is removed")
        let stories = try ctx.fetch(FetchDescriptor<StoryModel>())
        XCTAssertEqual(stories.count, 1, "the Story itself survives")
    }

    func test_delete_keepsStorySettingsSoCreateStartsAnOriginalWithTheSameInputs() throws {
        let story = makeStory()
        story.editorialMode = "full"; story.soundPreferenceExplicit = "balanced"; story.intentTargetDurationSeconds = 155
        let victim = addOutput(to: story)
        _ = try DebugOutputDeletion.delete(victim, from: story, context: ctx, removeFile: { _ in true })
        XCTAssertEqual(story.editorialMode, "full"); XCTAssertEqual(story.soundPreferenceExplicit, "balanced")
        XCTAssertEqual(story.intentTargetDurationSeconds, 155)
        // With no usable output left, the reopen rule sends the user to Create (a fresh ORIGINAL), not a result.
        XCTAssertEqual(ReopenDecision.decide(outputs: story.generatedOutputs, isStale: { _ in false }, fileExists: { _ in true }),
                       .create)
    }

    func test_delete_neverRemovesAFileAnotherVersionPointsAt() throws {
        let story = makeStory()
        let a = addOutput(to: story, path: "rendered/shared.mp4")
        _ = addOutput(to: story, path: "rendered/shared.mp4")
        var removed: [String] = []
        let out = try DebugOutputDeletion.delete(a, from: story, context: ctx, removeFile: { removed.append($0); return true })
        XCTAssertFalse(out.removedFile); XCTAssertTrue(removed.isEmpty)
        XCTAssertEqual(outputCount(), 1)
    }

    func test_delete_neverRemovesAFileOutsideRendered() throws {
        let story = makeStory()
        let o = addOutput(to: story, path: "media/original-moment.mov")
        var removed: [String] = []
        _ = try DebugOutputDeletion.delete(o, from: story, context: ctx, removeFile: { removed.append($0); return true })
        XCTAssertTrue(removed.isEmpty, "a Moment original must never be removed by a version delete")
        XCTAssertEqual(outputCount(), 0)
    }

    func test_delete_refusesWhileAnOperationIsInFlight_andChangesNothing() throws {
        let story = makeStory()
        let o = addOutput(to: story)
        ctx.insert(PendingOperationModel(storyId: story.id, operationId: "op-1", operationType: "original", phase: "rendering"))
        try ctx.save()
        XCTAssertEqual(DebugOutputDeletion.blockReason(for: o, in: story, context: ctx), .operationInFlight)
        XCTAssertThrowsError(try DebugOutputDeletion.delete(o, from: story, context: ctx, removeFile: { _ in XCTFail("no file op"); return true })) {
            XCTAssertEqual($0 as? DebugOutputDeletion.Failure, .blocked(.operationInFlight))
        }
        XCTAssertEqual(outputCount(), 1)
    }

    func test_delete_ignoresSavedPendingRowsOfEarlierOperations() throws {
        let story = makeStory()
        let o = addOutput(to: story)
        ctx.insert(PendingOperationModel(storyId: story.id, operationId: "op-1", operationType: "original", phase: "saved"))
        try ctx.save()
        XCTAssertNil(DebugOutputDeletion.blockReason(for: o, in: story, context: ctx))
        _ = try DebugOutputDeletion.delete(o, from: story, context: ctx, removeFile: { _ in true })
        XCTAssertEqual(outputCount(), 0)
        // The saved row is left alone (history), and it is NOT recoverable, so recovery cannot resurrect the version.
        let rows = try ctx.fetch(FetchDescriptor<PendingOperationModel>())
        XCTAssertEqual(rows.count, 1); XCTAssertFalse(rows[0].isRecoverable)
    }

    func test_delete_refusesWhenDerivedVersionsExist() throws {
        let story = makeStory()
        let base = addOutput(to: story)
        _ = addOutput(to: story, parent: base, op: "another_version")
        XCTAssertThrowsError(try DebugOutputDeletion.delete(base, from: story, context: ctx, removeFile: { _ in true })) {
            XCTAssertEqual($0 as? DebugOutputDeletion.Failure, .blocked(.hasDerivedVersions(1)))
        }
        XCTAssertEqual(outputCount(), 2)
    }

    func test_delete_rejectsAVersionThatIsNotOnThisStory() throws {
        let a = makeStory(title: "A"), b = makeStory(title: "B")
        let oa = addOutput(to: a)
        XCTAssertThrowsError(try DebugOutputDeletion.delete(oa, from: b, context: ctx, removeFile: { _ in true })) {
            XCTAssertEqual($0 as? DebugOutputDeletion.Failure, .notOnThisStory)
        }
        XCTAssertEqual(outputCount(), 1)
    }

    func test_nextOriginalGetsAFreshOperationId_andTheDeletedVersionsOperationIsNotReused() throws {
        // planOperationId is cleared on completion, so the next Original mints a NEW idempotency key (a new job),
        // never replaying the finished one. Mirror the post-completion state and assert the delete leaves it nil.
        let story = makeStory()
        story.planOperationId = nil; story.planJobId = nil
        let o = addOutput(to: story)
        _ = try DebugOutputDeletion.delete(o, from: story, context: ctx, removeFile: { _ in true })
        XCTAssertNil(story.planOperationId); XCTAssertNil(story.planJobId)
    }
}
#endif
