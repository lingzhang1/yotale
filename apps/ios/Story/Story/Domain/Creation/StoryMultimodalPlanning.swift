import Foundation

// StoryMultimodalPlanning — versioned creative brief + the retained critique-pass setting for multimodal
// visual edit planning.
//
// P1-G0: multimodal (Visual-first) planning is STANDARD behavior — the former STORY_MULTIMODAL_PLANNING
// kill-switch and the STORY_CRITIQUE_EXPLORE opt-in were removed. The coordinator builds bounded Tier-1
// contact sheets, runs the adaptive visual-budget preflight, and plans through the async edit-plan job with
// graceful text-only fallback. `critiqueRevisionEnabled` is DELIBERATELY RETAINED (owner decision): it is the
// latency/cost lever for the 3-call original-create path.
//
// The creative brief string + version MUST stay in sync with the backend (apps/api MM_CREATIVE_BRIEF /
// MM_CREATIVE_BRIEF_VERSION). It is injected into the Edit Planner USER message only — never the frozen body.
enum StoryMultimodalPlanning {
    /// Phase-6 / experiment Arm D: run ONE bounded critique->revision pass on a Visual-first plan. Arm D was
    /// the LARGEST quality lever in the short-form creative-objective experiment (fixes the hook, finds omitted
    /// /repetitive footage), so for the best-results MVP it is DEFAULT ON. It costs 2 extra model calls per
    /// create (each re-sending the ~3 MB image payload) and is quota-fragile, so a kill-switch remains:
    /// env `STORY_CRITIQUE_REVISION=0` or UserDefaults bool `STORY_CRITIQUE_REVISION=false` forces it OFF
    /// without a rebuild. Absent any override it is ON. RETAINED ON PURPOSE (owner): kept so the critique pass
    /// can be tuned/disabled for latency work without a code change.
    static var critiqueRevisionEnabled: Bool {
        if ProcessInfo.processInfo.environment["STORY_CRITIQUE_REVISION"] == "0" { return false }
        if ProcessInfo.processInfo.environment["STORY_CRITIQUE_REVISION"] == "1" { return true }
        if UserDefaults.standard.object(forKey: critiqueFlagKey) != nil {
            return UserDefaults.standard.bool(forKey: critiqueFlagKey)
        }
        return _critiqueDefault
    }
    static let critiqueFlagKey = "STORY_CRITIQUE_REVISION"
    static func setCritiqueOverride(_ on: Bool) { UserDefaults.standard.set(on, forKey: critiqueFlagKey) }
    private static let _critiqueDefault = true

    static let creativeBriefVersion = "shortform_mvp/1"
    static let creativeBrief = """
    When user intent does not require chronology, prioritize visually engaging and meaningful footage. \
    Find a compelling opening, construct coherent visual progression, preserve important actions and \
    payoffs, and choose shot durations appropriate to the material. Do not force a conventional \
    travel-diary structure.
    """
}

/// Per-run multimodal planning diagnostics (NO image bytes/content) — surfaced for device-acceptance
/// verification so a device run can PROVE whether multimodal or text-only planning was used, which tier, and
/// why any fallback happened.
struct StoryPlanningDiagnostics {
    let usedMultimodal: Bool
    let sheetCount: Int
    let imageBytes: Int
    let momentsTextOnly: Int
    let selectedTier: String
    let appliedSteps: [String]
    let fallbackReason: String?
    let creativeBriefVersion: String?
    // Phase-4 fallback transparency: the user's REQUESTED editing approach vs what ACTUALLY ran. When
    // Visual-first falls back to text-only, requested stays .visualFirst while actual becomes .storytelling,
    // and usedMultimodal is false — so we never claim the footage was visually analyzed when it was not.
    var requestedApproach: EditingApproach = .storytelling
    var actualApproach: EditingApproach = .storytelling
}
