#if DEBUG
import Foundation
import SwiftData

// DebugOutputDeletion — DEBUG-ONLY "Delete this version" for controlled planner evaluations (EditPlan 5.3 vs 5.5).
//
// WHY: a Story with an exported video re-opens that video when you tap Create, and the app has no way to remove a
// version, so a second ORIGINAL (a different planner version on the SAME Story, Moments, Guide, Coverage and music
// plan) could not be produced. This removes ONE version so Create starts a fresh Original on the same Story.
//
// This whole file is compiled only in DEBUG builds (TestFlight/App Store builds contain none of it). It is NOT a
// product feature: it deliberately has no localized copy, no Settings entry and no cloud deletion.
//
// WHAT IT REMOVES (this device + the synced Story document):
//   - the GeneratedOutputModel row (the version),
//   - its rendered MP4 under <Documents>/rendered/ (only when no other version points at the same file),
//   - the output's cloud-backup queue rows (GeneratedOutputBackupJobModel) so no upload runs for a deleted version.
// WHAT IT KEEPS: the Story, its Moments and media, Guide, Coverage, MusicPlan, intent, duration choice, editorial
// type, sound preference, creative direction, every other version and every pending-operation row.
// WHAT IT DOES NOT TOUCH: the cloud copy of the rendered MP4 (cloud deletion is an account-deletion policy decision,
// design-only). The caller marks the Story dirty so the next sync push writes a doc WITHOUT the version; a pull never
// re-adds it because pulls apply only to clean records and the server revision is unchanged.
//
// SAFETY: refuses while an operation is in flight on the Story, and while newer versions derive from this one
// (Explore/Revise/Change-Music children), so no lineage is left dangling.
enum DebugOutputDeletion {

    enum Block: Equatable {
        case operationInFlight
        case hasDerivedVersions(Int)

        var explanation: String {
            switch self {
            case .operationInFlight:
                return "A video is still being created for this Story. Wait for it to finish, then try again."
            case .hasDerivedVersions(let n):
                return "\(n) newer version\(n == 1 ? "" : "s") (Explore, Revise or Change Music) derive from this one. Delete those first."
            }
        }
    }

    enum Failure: Error, Equatable {
        case blocked(Block)
        case notOnThisStory
    }

    struct Outcome: Equatable {
        var removedFile: Bool
        var backupJobsRemoved: Int
        var relativePath: String?
    }

    // MARK: - Pure decisions (unit-tested)

    /// Why this version cannot be deleted right now, or nil when it can.
    /// `pendingPhases` are the `phase` values of the Story's PendingOperationModel rows.
    static func block(for output: GeneratedOutputModel,
                      amongStoryOutputs outputs: [GeneratedOutputModel],
                      pendingPhases: [String]) -> Block? {
        if pendingPhases.contains(where: { $0 != "saved" && $0 != "abandoned" }) { return .operationInFlight }
        let children = outputs.filter { $0.id != output.id && $0.parentVersionId == output.versionId }.count
        return children > 0 ? .hasDerivedVersions(children) : nil
    }

    /// The relative path of the MP4 that may be removed with this version, or nil. Only files under `rendered/` with
    /// no traversal and not shared with another version are eligible; anything else is left alone.
    static func deletableFile(relative: String?, usedByOtherVersions: Set<String>) -> String? {
        guard let rel = relative, !rel.isEmpty,
              rel.hasPrefix("rendered/"), !rel.hasPrefix("/"), !rel.contains(".."),
              !usedByOtherVersions.contains(rel) else { return nil }
        return rel
    }

    // MARK: - Action

    /// Dry run of the guards `delete` applies, so a caller can refuse BEFORE changing any view or model state.
    @MainActor
    static func blockReason(for output: GeneratedOutputModel, in story: StoryModel, context: ModelContext) -> Block? {
        let sid = story.id
        let pendingDesc = FetchDescriptor<PendingOperationModel>(predicate: #Predicate { $0.storyId == sid })
        let phases = ((try? context.fetch(pendingDesc)) ?? []).map(\.phase)
        return block(for: output, amongStoryOutputs: story.generatedOutputs, pendingPhases: phases)
    }

    /// Deletes `output` from `story`. Throws `Failure.blocked` before changing anything; on a persistence error the
    /// context is rolled back and the error rethrown. `removeFile` is injectable so tests never touch the disk.
    @MainActor
    @discardableResult
    static func delete(_ output: GeneratedOutputModel,
                       from story: StoryModel,
                       context: ModelContext,
                       removeFile: (String) -> Bool = { rel in
                           (try? FileManager.default.removeItem(at: RenderOutputStore.shared.absoluteURL(for: rel))) != nil
                       }) throws -> Outcome {
        let oid = output.id
        let sid = story.id
        guard story.generatedOutputs.contains(where: { $0.id == oid }) else { throw Failure.notOnThisStory }

        if let b = blockReason(for: output, in: story, context: context) { throw Failure.blocked(b) }

        // A file is removed only if NO other version (on any Story) points at it.
        let allOutputs = (try? context.fetch(FetchDescriptor<GeneratedOutputModel>())) ?? []
        let usedElsewhere = Set(allOutputs.filter { $0.id != oid }.compactMap(\.relativeFilePath))
        let filePath = deletableFile(relative: output.relativeFilePath, usedByOtherVersions: usedElsewhere)

        let jobDesc = FetchDescriptor<GeneratedOutputBackupJobModel>(predicate: #Predicate { $0.outputId == oid })
        let jobs = (try? context.fetch(jobDesc)) ?? []
        for j in jobs { context.delete(j) }

        context.delete(output)
        story.updatedAt = .now
        do {
            try context.save()
        } catch {
            context.rollback()
            throw error
        }

        // Remove the bytes only after the rows are gone, so a failed save never leaves a version without its file.
        let removed = filePath.map(removeFile) ?? false
        return Outcome(removedFile: removed, backupJobsRemoved: jobs.count, relativePath: filePath)
    }
}
#endif
