# C3B Director Model-Ceiling Comparison

**Date:** 2026-10-02
**Rule honored:** changed ONLY the model. Same prompt (`story_director/v1`),
contracts, 15-fixture corpus, deterministic guards, structured-output schema.
**Outcome: B — Opus 4.5 materially outperforms; use it for C3B. Do not optimize cost yet.**

## Candidate availability (account 989088054552 / us-east-1, queried live)
Requested Sonnet 5.5 / Opus 5.5 are **in the console catalog but NOT invocable** —
`AccessDeniedException: not available for this account` (the 5.5 tier needs its own
Model-access enablement, separate from the Anthropic use-case form). After the
account's Anthropic use-case form was filed, the **4.5 tier became invocable**:
- Baseline: `amazon.nova-pro-v1:0`
- Sonnet production candidate: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- Opus ceiling candidate: `us.anthropic.claude-opus-4-5-20251101-v1:0`

So the comparison is the three-tier shape requested, at the **4.5 generation** (the
5.5 generation was not reachable; re-run this harness on 5.5 once enabled).

## Engine fix exposed by the stronger model (not prompt-tuning, not model-specific)
`_integrity_guard` wrongly required a non-empty plan for EVERY decision. A
`rescan_scene` / `create_now` decision legitimately carries NO plan (the Director
is declining to plan). Opus's correct `rescan_scene` on the irrelevant scene was
being rejected by the guard. Fixed: empty plan allowed only for rescan/create;
`capture_shot`/`retry_shot` still require beats + a shot. 98 pytest green.

## Aggregate (15-fixture corpus)
| metric | Nova Pro | Sonnet 4.5 | **Opus 4.5** |
|---|---|---|---|
| contract validity | 15/15 | 14/15 (1 transient) | **15/15** |
| mean beats | 2.53 | 1.64 | **1.27** |
| mean shots | 2.73 | 1.57 | **1.13** |
| capture_shot | 14 | 13 | 12 |
| rescan_scene | **0** | **0** | **2** |
| create_now | 1 | 1 | 1 |
| latency p50 | 4.0s | 16.0s | 11.0s |
| latency p90 | 5.1s | 21.5s | 13.8s |
| mean tokens | 4.8k | 5.9k | 5.6k |

## Critical narrative-grounding triad
**A — TMB + backpack/home (relevant).** All three find the preparation bridge.
Quality rises with the model: Nova "medium shot of the backpack" →
Opus "The Weight Before the Trail — hold steady on the backpack with the window
light behind it."

**B — TMB + unrelated music/office room (rescan preferred).**
- Nova: "Preparation for an 8-day TMB hike", 3 beats / 5 shots, **wide shot of the
  room including guitar/desk** — the exact device failure, reproduced.
- Sonnet: trimmed to 1/1 but STILL forced it ("move toward the guitar") — still
  manufacturing a hiking connection.
- **Opus: `rescan_scene`** — reason: "no visual elements meaningfully serve a Tour
  du Mont Blanc hiking Story … no hiking gear, no backpacks, no maps." Correct.

**C — music intent + SAME room (relevant).**
- Opus: `capture_shot`, "The Quiet Work of Getting Better — frame the guitar and
  music stand, your practice corner." USES the same room when the intent makes it
  relevant → proves genuine narrative judgment, NOT blanket rejection of ordinary
  rooms. (Nova gave an object-inventory wide shot; Sonnet had a transient fail.)

## Minimum-sufficient capture (long Story + low-value scene)
`dir_mincap_longstory_lowvalue` (60s TMB Story + music room):
- Nova 3 beats / 7 shots (worst over-planning yet).
- Sonnet 1/1 but still a forced TMB pan.
- **Opus `rescan_scene`** — recognizes the scene contributes nothing to the Story.
Opus clearly separates final-Story duration from current-scene contribution.

## Quality dimensions (summary)
Opus 4.5 best on narrative grounding, minimum-sufficient capture, concept strength
("let the stillness speak", "let it breathe for 5-6 seconds"), and instruction
quality; equal on scene grounding and intent/scene sensitivity; passed safety
(ridge case = conservative follow shot, no backward-near-edge). Validity 15/15.
Cost: slower (p50 11s) and pricier per call than Nova, but the task says quality is
the primary criterion and not to reject Opus for speed/cost.

## Decision
**Outcome B.** Opus 4.5 solves both C3-blocking failures that Nova and Sonnet do
not. Director default set to `us.anthropic.claude-opus-4-5-20251101-v1:0`
(config `STORY_DIRECTOR_MODEL`). Sonnet-approaching-Opus-via-prompting and the
5.5-tier comparison are deferred follow-ups, not C3 blockers.

## Next
Deploy Opus 4.5 → physical-iPhone re-test the 4 scenarios (TMB+backpack,
TMB+music room [expect rescan], relevant-intent+same room, one rich scene) →
record real-device quality + latency → C3 close gate. NOT starting C4.
