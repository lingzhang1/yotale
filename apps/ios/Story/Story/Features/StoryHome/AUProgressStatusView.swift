import SwiftUI
import SwiftData

/// Honest Asset Understanding status for Story Home. Every word comes from the PERSISTED queue rows
/// (AssetUnderstandingJobModel) mapped by AUQueueStatusMapper — no timers, no guessed percentages. The @Query
/// makes it re-render whenever the queue writes a state change; the live facts (network, a drain running, a
/// system background task running) are read at render time.
struct AUProgressStatusView: View {
    let momentIds: Set<UUID>
    /// Shown when the queue has nothing to report for this Story (the readiness copy stays the source of truth).
    let fallback: String
    let foreground: Color

    @Environment(\.modelContext) private var context
    @Query private var jobs: [AssetUnderstandingJobModel]

    var body: some View {
        let snapshot = AssetUnderstandingQueue.snapshot(context: context, momentIds: momentIds)
        let line = AUQueueStatusMapper.line(snapshot, continuesInBackground: AUContinuedProcessing.isRunning)
        VStack(spacing: 4) {
            Text(line ?? fallback)
                .font(StoryTheme.body(11))
                .foregroundStyle(foreground)
                .multilineTextAlignment(.center)
            if AUQueueStatusMapper.offersRetry(snapshot) {
                Button("Retry") {
                    let q = AssetUnderstandingQueue(context: context)
                    q.retryParked()
                    AUContinuedProcessing.startAfterImport(queue: q, context: context)
                }
                .font(StoryTheme.body(11))
                .foregroundStyle(StoryTheme.cream.opacity(0.7))
                .accessibilityHint("Tries the Moments that couldn't be analyzed again")
            }
        }
        .accessibilityElement(children: .combine)
        // `jobs` is read only to subscribe this view to queue writes.
        .accessibilityIdentifier("au-status-\(jobs.count)")
    }
}
