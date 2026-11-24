import Foundation

// StoryMultimodalPlanning — versioned creative brief + the retained critique-pass setting for multimodal
// visual edit planning.
//
// P1-G0: multimodal (Visual-first) planning is STANDARD behavior — the former STORY_MULTIMODAL_PLANNING
// kill-switch and the STORY_CRITIQUE_EXPLORE opt-in were removed. The coordinator builds bounded Tier-1
// contact sheets, runs the adaptive visual-budget preflight, and plans through the async edit-plan job with
// graceful text-only fallback. `critiqueRevisionEnabled` is DELIBERATELY RETAINED (owner decision) and defaults
// OFF: a plain original create plans in ONE call. Turning it on adds the 3-call critique->revision path.
//
// The creative brief string + version MUST stay in sync with the backend (apps/api MM_CREATIVE_BRIEF /
// MM_CREATIVE_BRIEF_VERSION). It is injected into the Edit Planner USER message only — never the frozen body.
enum StoryMultimodalPlanning {
    /// Phase-6 / experiment Arm D: ONE bounded critique->revision pass on a Visual-first plan. DEFAULT OFF
    /// (owner decision 2026-11-15): measured on dev, the pass turned a ~16 s single planning call into a 37-44 s
    /// three-call job (about +20-28 s) and re-sends the ~3 MB image payload on every call, and no
    /// same-footage comparison shows it improves the shipped plan. The setting is RETAINED so it can still be
    /// turned ON without a code change: env `STORY_CRITIQUE_REVISION=1` or UserDefaults bool
    /// `STORY_CRITIQUE_REVISION=true`. Env/UserDefaults `0`/`false` force it OFF. Absent any override it is OFF.
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
    private static let _critiqueDefault = false

    /// PURE decision (unit-tested): does this planning call run the critique -> revision pass?
    ///  • not multimodal, or the retained `critiqueRevisionEnabled` setting is off (the default) -> no
    ///  • Explore ("Create Another Version") -> NEVER (one planning call; the old opt-in was removed)
    ///  • a TARGETED revise (Path B) -> no (a bounded change, not a creative re-edit)
    ///  • original create / full re-edit (Path C) -> yes, but ONLY when the setting has been turned on
    static func critiqueApplies(wantMultimodal: Bool, critiqueEnabled: Bool, isExplore: Bool,
                                reviseScope: RevisionScope?) -> Bool {
        guard wantMultimodal && critiqueEnabled else { return false }
        if isExplore { return false }
        if let scope = reviseScope, scope != .fullReedit { return false }
        return true
    }

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
