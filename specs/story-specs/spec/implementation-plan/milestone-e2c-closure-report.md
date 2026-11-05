# Milestone E2-c — Closure & Device-Acceptance Report

**Status:** E2-c ACCEPTED & CLOSED (owner, 2026-10-07, physical-iPhone verified). The full frozen
E2 architecture (CreativeIntent → StoryGuide → Mapper → Judge → Coverage/2 → Guide/Idea UX → both
Director entry points) is implemented, deployed to the dev App Runner, and device-accepted.

## Owner-verified critical paths (all pass on device)
new StoryGuide generation · "Here's what I'll look for" · persistent Story Guide · StoryCoverage/2
updates · Story Idea · Guide possibility → Shoot · Story Idea → Show me · selected_opportunity
reaches Director · supported scenes → appropriate recommendation · unsupported scenes → rescan_scene
· AU/Coverage lifecycle · existing-Story migration · persistence / reopen.

## Device-gate fixes shipped during acceptance (iOS-only, no redeploy)
- `994650d` — (1) existing-Story Guide loading robustness (always clears loading; "Build my guide"
  retry) → fixed the SF "Thinking about your Story…" hang; (2) `refreshAfterCapture` polls ~60s for
  the just-captured Moment's async AU to land, then recomputes Coverage/2 + Story Idea → fixed
  "Idea won't update after a Moment"; (3) scan modal shows the selected opportunity (CAPTURING + label
  + purpose) instead of a context-free "Show me what's around you".
- `1f5c379` — scan-intro polish: single serif headline (the opportunity), scan instruction demoted to
  a quiet subtitle (no competing titles), all fonts on StoryTheme tokens (consistency with Story Home).

## Full E2-c commit set
Backend `4a7317a` (Guide engine + /v1/story-guide; Coverage/2 Mapper+Judge+firewall + /v1/story-coverage/v2).
Director `a14c91b` (selected_opportunity additive, D1–D5), `e060806` (Equatable fix). iOS batches:
`2dfda62` (lifecycle), `cedf6a9` (wizard), `d11a028` (Guide UX), `618b206` (Director entry points),
`5df9046` (tests + production gate), `994650d` + `1f5c379` (device-gate fixes). Specs: E2 reconciliation,
E2-a/E2-b experiment+freeze reports, E2-c Phase-1 reconciliation + this closure.

## Deployment (live, verified)
Dev App Runner (ydmju5wdps): /health 200; /v1/story-guide + /v1/story-coverage/v2 live; C1/C2/C3/AU
no regression; Director with/without selected_opportunity both correct. Deployed via throwaway
CodeBuild+ECR (torn down). No new AWS infrastructure.

## NON-BLOCKING dogfood UX findings (recorded for LATER refinement — NOT fixed now, owner's instruction)
1. **Checklist resemblance.** The Guide's capture possibilities, rendered as repeated empty-circle +
   "Shoot →" rows, can visually read like a checklist despite the "a guide, not a checklist" framing and
   the advisory semantics underneath. Candidate future refinements (none chosen): fewer visible
   possibilities per dimension, a lighter/inspiration-styled affordance, progressive disclosure, or
   showing possibilities only on tap. Reasoning layer is correct; this is pure presentation.
2. **Vertical length.** A richer Guide (e.g. 3 dimensions × ~2–3 possibilities + framing + Coverage
   overlay) becomes a long scroll that dominates Story Home below the moments mosaic. Candidate future
   refinements (none chosen): collapse dimensions by default, cap visible possibilities, or a dedicated
   Guide detail screen. Watch alongside finding #1 — both point at the same "possibility density" lever.

Both are UX-presentation items, not reasoning/architecture regressions. Revisit in a dedicated dogfood
UX pass, separately from the frozen Coverage/Guide intelligence.

## E2-c CLOSED. Next roadmap step: Music milestone — DESIGN RECONCILIATION ONLY (no implementation).
