# C3B Director-Quality Iteration — Before/After Report

**Date:** 2026-10-02
**Scope:** ONE general Director prompt iteration targeting the two device-confirmed
failure patterns (over-planning; scene-grounded-but-narratively-irrelevant
direction). No case-tuning. No C4. **C3 is NOT closed — see gate below.**

## What changed (general, not case-tuned)
`prompts/story_director/v1/system.md`:
- **NARRATIVE GROUNDING** principle: a recommendation must be BOTH scene-grounded
  AND narratively grounded (the "viewer test"); a concept label cannot manufacture
  relevance the footage wouldn't show; explicit ban on object-inventory wide-shot
  fallbacks.
- **THE CURRENT SCENE IS NOT THE WHOLE STORY**: distinguish final-Story
  scope/duration from this scene's contribution; justify every added beat/shot;
  no padding to fill duration; no fixed maximum.
- **rescan_scene widened** to "no genuine narrative bridge" and framed as a
  first-class correct outcome for a low-value scene.
- (A second, stronger PROCEDURAL variant — a forced relevance-gate step order —
  was tried and REVERTED: it regressed Nova Pro further and broke structured-output
  validity. See results.)

New regression fixtures (corpus now 15):
- `dir_narrative_grounding_axis`: **A** TMB+home/backpack (relevant ordinary),
  **B** TMB+music/office room (irrelevant ordinary → `NARRATIVE_GROUNDING_FAILURE`,
  rescan preferred), **C** music-intent+same music room (relevant intent — proves
  ordinary rooms are usable when relevant).
- `dir_mincap_axis`: long-story+low-value scene, short casual Moment, genuinely
  rich scene (multiple shots justified), weak scene (one shot).
New harness `evals/run_director_corpus.py` records beats/shots/decision per case.

## Before / after (model `amazon.nova-pro-v1:0`, full 15-fixture corpus)

| metric | BEFORE | AFTER (principles) | AFTER2 (procedural, reverted) |
|---|---|---|---|
| mean beats | 2.73 | 2.80 | 2.69 |
| mean shots | 2.67 | 2.87 | 2.85 |
| `rescan_scene` chosen | 0/15 | 0/15 | 0/15 |
| `capture_shot` | 15/15 | 15/15 | 13/15 |
| validity failures | 0 | 0 | **2** |

Key cases:
- **`dir_ng_B` (TMB + irrelevant music room)** — the headline case. BEFORE:
  "Preparation for an 8-day TMB hike", 3 beats/3 shots, capture_shot. AFTER:
  same concept, 3/4. AFTER2: same concept, 4/5. **In every variant the Director
  manufactured a TMB story from a music room and never chose `rescan_scene`.**
- **`dir_mincap_longstory_lowvalue`** — BEFORE 3/4, AFTER 4/4, AFTER2 4/6.
  Over-planning on a low-value scene did not improve; it drifted worse.
- Relevant cases stayed fine (A finds a real preparation bridge; C uses the music
  room for a music intent; trail/scale/safety unchanged), so the rules did not
  over-correct into blanket rejection — but they also did not achieve the intended
  behavior change.

## Honest finding: this is a MODEL-capability limit, not a prompt-wording problem
Three prompt formulations (reworded principles, then a forced procedural
relevance-gate) all failed to make `amazon.nova-pro-v1:0`:
1. decline an irrelevant scene via `rescan_scene` (0/15 every time), or
2. reduce over-planning / scale capture to scene value.

Heavier, more explicit instructions made its structured output LESS reliable
(AFTER2: 2 validity failures). Nova Pro reliably GROUNDS objects and emits
structure, but does not perform the narrative-relevance judgment or the
minimum-sufficient restraint these patterns require. This matches the risk the
C3 brief named ("do not assume Nova is right for the Director").

The intended remedy — a stronger reasoning model — is already supported
(config-driven `STORY_DIRECTOR_MODEL`). The candidate (Claude Sonnet 4.5) remains
**Anthropic use-case-gated for this account** (re-checked this session:
`ResourceNotFoundException … use case details have not been submitted`).

## Actions taken
- Kept the correct principle-level rules + widened `rescan_scene` (harmless on
  Nova Pro, and correct for a capable model). Reverted the procedural variant.
- Added the fixtures + corpus harness so the SAME before/after can be re-run on
  Claude in minutes once access is granted.
- **Did NOT redeploy / did NOT device-retest.** Redeploying this prompt on Nova
  Pro would reproduce the same weak behavior (dir_ng_B still forces a TMB story on
  a music room) and waste a build + a device session. The device re-test is
  worth running only behind a model that moves the corpus metrics.
- 98 backend pytest green; corpus 15/15 valid on the reverted prompt.

## C3 close gate — BLOCKED (needs a human-only action)
C3 close requires the real-device Director to demonstrate narrative grounding,
useful low-value-scene rejection, and minimum-sufficient planning. On the only
reliably-accessible model those three are not met, and prompt iteration cannot
reach them. **To close C3, submit the Anthropic Bedrock use-case form for this
account** (console → Bedrock → Model access → Anthropic Claude), after which I:
1. flip `STORY_DIRECTOR_MODEL` to `us.anthropic.claude-sonnet-4-5-20250929-v1:0`,
2. re-run this exact before/after corpus on Claude,
3. redeploy only if the metrics improve (rescan on irrelevant scenes;
   scene-scaled beat/shot counts; no narrative-grounding failures),
4. run the 4-scenario physical-iPhone re-test and close C3.

If Anthropic access cannot be granted, the honest alternative is to accept the
current Nova Pro quality as the C3 ceiling and record the two patterns as known
limitations carried into C4 — a product call, not an engineering one.

## Do NOT proceed to C4 (Shot Validation) — per instruction.
