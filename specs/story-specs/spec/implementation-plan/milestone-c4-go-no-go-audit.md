# C4 Shot Validation — PRODUCT GO/NO-GO audit (≤10s DIRECT-like band)

Status: **AUDIT — decision requested. Do NOT assume C4B is built.**
Date: 2026-10-05. Author: default (Kiro). Model NOT optimized during this audit.

Question audited: *does an immediate semantic validator improve the user's capture
experience enough to justify its latency (~4–5s/capture), recurring inference cost,
complexity, and errors?* Evidence: the C4A.2 live run (uniform-4 ordered frames +
Sonnet 4.6, the recommended frontier), ≤10s band, n=28. Result file
`evals/results/c4a2_capture_evidence_20261005T043200Z.json`.

---

## The number that drives the decision

**≤10s user-state accuracy = 17/28 = 0.61.** Of the **11 errors, 10 are false
GOT IT** (model says the requested moment was captured when it was not); only 1 is
over-cautious. In a capture product, false GOT IT is the **worst** error: the user
walks away believing they have the shot, and discovers at edit time that they don't —
when the moment is gone and unrepeatable. This band is the DIRECT-like primary use
case (short, purpose-driven captures), i.e. exactly where C4 must be trustworthy.

Direction of the 11 errors:
- **7 × FALSE_ACCEPT vs try_again** (should discard/retry → said GOT IT)
- **3 × FALSE_ACCEPT vs keep+one_more** (requested shot unfulfilled but useful → said GOT IT)
- **1 × over-cautious** (good shot → keep+one_more)

## Per-failure product-impact classification (all 11 ≤10s failures)

| fixture | exp → pred (user-state) | root cause | PRODUCT IMPACT |
|---|---|---|---|
| `T01_B_too_short` | try_again → got_it | 0.47s clip; model called it usable/fulfilled | **HARMFUL_FALSE_ACCEPT** → but a **deterministic duration gate catches it** (becomes HARMLESS once gated) |
| `T01_B_too_short_08s` | try_again → got_it | same, second too-short clip | **HARMFUL_FALSE_ACCEPT** → **deterministic duration gate catches it** (HARMLESS once gated) |
| `S01_B_stand_still` | keep+one_more → got_it | requested a *departure*; subject stood still; no motion = unfulfilled, but model saw the scene and said fulfilled | **HARMFUL_FALSE_ACCEPT** (temporal; purely semantic — no gate catches it) |
| `S05_E_static_camera_two_people` | keep+one_more → got_it | requested trail *progression*; static framing; model accepted | **HARMFUL_FALSE_ACCEPT** (temporal; purely semantic) |
| `S07_E_wrong_people` | keep+one_more → got_it | requested companionship with the *right* people; wrong subjects present; model accepted | **HARMFUL_FALSE_ACCEPT** (wrong-subject; purely semantic) |
| `T01_D_severe_shake` | try_again → got_it | model rated severe shake as only minor_issues/partial → GOT IT | **HARMFUL_FALSE_ACCEPT** (technical; the model does NOT reliably catch gross technical failure) |
| `T01_G_out_of_focus` | try_again → got_it | out-of-focus rated usable → GOT IT | **HARMFUL_FALSE_ACCEPT** (technical; the approved design explicitly left focus to the *model*, and the model misses it) |
| `T01_I_camera_points_away` | try_again → got_it | subject absent (camera pointed away) rated partial → GOT IT | **TRUST_BREAKING** (tells the user they got a shot of a subject that is not in frame) |
| `T01_E_underexposed` | try_again → got_it | severe underexposure rated minor → GOT IT | **HARMFUL_FALSE_ACCEPT** (a cheap exposure heuristic *might* catch it; the model alone does not) |
| `T01_F_overexposed` | try_again → got_it | severe overexposure rated minor → GOT IT | **HARMFUL_FALSE_ACCEPT** (same) |
| `T01_E_tired_face` | got_it → keep+one_more | model under-credited a fulfilling clip | **MINOR** (over-cautious; one unnecessary "let's get one more", no lost footage) |

### Impact tally (≤10s, n=28)
- **TRUST_BREAKING: 1** (`camera_points_away` → GOT IT on an absent subject)
- **HARMFUL_FALSE_ACCEPT: 9** — of which **2** are cleanly removed by the deterministic
  duration gate (the too-short pair), leaving **7 that survive gating**: 3 temporal/
  subject semantic (`stand_still`, `static_two_people`, `wrong_people`) + 4 technical
  the model should have caught but didn't (`severe_shake`, `out_of_focus`,
  `underexposed`, `overexposed`; exposure *may* be heuristic-catchable, shake/focus
  not currently).
- **HARMFUL_FALSE_RETRY: 0** (good news — the validator is not over-rejecting good shots)
- **MINOR: 1** (`tired_face` over-cautious)
- **HARMLESS: 0** pure (the 2 gated too-short become harmless only *because of the
  deterministic gate*, not the semantic model)

**Net:** after applying the one approved deterministic gate (duration), the semantic
validator still produces **8 harmful-or-worse ≤10s verdicts out of 28 (29%)**, almost
all false GOT IT, including one trust-breaking case. The validator's *purpose* — catch
when the requested moment was NOT captured — is exactly what it fails at here.

## Why this is not a "tune the model" problem for the go/no-go

The audit brief forbids optimizing the model, correctly: the decision is about the
*product shape*, and two findings are structural, not prompt-tuning noise:

1. **The semantic model does not reliably catch gross technical failure** (shake,
   focus, exposure, subject-absent all → GOT IT). The approved C4 design deliberately
   routed focus/quality to the *model*. This audit shows that assumption is unsafe for
   ≤10s: those belong in **deterministic/local checks**, not the multimodal model.
2. **The remaining pure-semantic misses are false ACCEPTS on temporal/subject intent**
   (`stand_still`, `static_two_people`, `wrong_people`) — the model sees a plausible
   scene and says "fulfilled" without honoring the requested *action/subject*. That is
   the hard core of semantic validation, and at 0.61 ≤10s accuracy it is not yet at a
   level where shipping it *in the capture loop* helps more than it misleads.

## Latency & cost as product factors (not just metrics)

- **Latency ~4–5s per capture** (p50 4.09s, p95 5.75s, Sonnet 4.6). In a capture
  flow, that is a 4–5s blocking "checking…" wait after every shot, for a verdict that
  is wrong ~39% of the time on short clips and wrong in the *dangerous* direction.
  The user would learn to distrust and skip it — negative product value.
- **Recurring inference cost:** every capture triggers a multimodal call (~15k input
  tokens of frames). At Sonnet 4.6 rates that is a per-capture cost on every shot a
  user takes, forever — a real COGS line for a feature that, on the primary band, is
  not yet trustworthy.
- **Complexity:** a live inference dependency in the capture hot path (network,
  throttling, timeout, retry UX) added for a 0.61-accuracy signal.

A feature that adds 4–5s + per-shot cost + a trust-breaking failure mode, to deliver a
≤10s verdict that is wrong in the harmful direction ~29% of the time, does **not**
currently clear the product bar.

## What DOES earn its place

The **deterministic/local checks** are cheap (sub-ms, on-device, no network, no
per-shot cost) and unambiguously helpful: duration cleanly caught the only 2 failures
it was given, and exposure is plausibly heuristic-catchable. These give the user
*instant, trustworthy* capture-integrity feedback ("too short", "too dark", "hold
steadier") with none of the latency/cost/complexity of the semantic model — and
without the false-GOT-IT failure mode, because they only ever flag *obvious* integrity
problems, never claim semantic fulfillment.

The **semantic Shot/Beat judgment** is better suited to run **asynchronously, offline,
as Asset Understanding** — no capture-loop latency, batch cost instead of per-shot,
and (per the C4A.2 finding) a context where intent-independent evidence and whole-clip
reasoning are natural. The Director loop can then consume *settled* semantic signal
rather than a 4–5s-blocking, 0.61-accurate inline guess.

---

## RECOMMENDATION

### **B — BUILD C4-LITE.**

Keep only **deterministic/local capture-integrity checks** in the capture loop
(duration now; exposure/shake/focus heuristics *only where they empirically earn it*,
per the standing Stage-1 caution). Give the user instant, trustworthy integrity
feedback. **Move semantic Shot/Beat understanding into asynchronous Asset
Understanding**, where it runs offline without per-capture latency/cost and where the
0.61 ≤10s semantic accuracy can be improved without a trust-breaking inline failure
mode.

**Not A (BUILD FULL C4):** immediate semantic validation at 0.61 ≤10s accuracy, 10/11
errors false-GOT-IT (one trust-breaking), + 4–5s + per-shot cost, is net-negative in
the capture loop today.

**Not C (DEFER C4):** doing nothing wastes the clearly-positive deterministic checks,
which are cheap and trustworthy and improve capture now.

### What C4-LITE means concretely (for a follow-up decision, NOT built here)
- Capture loop: `RealShotValidationEngine` becomes a **deterministic integrity gate**
  (duration + empirically-validated exposure; shake/focus only if they pass the T01
  false-rejection bar). Output maps to the existing user states: a hard integrity fail
  → **TRY AGAIN**; otherwise **GOT IT (provisional)** with NO semantic claim.
- The simple external `ValidationResult` stays; the internal 4-axis
  `ShotValidationJudgment` and its derivation **move to Asset Understanding** input,
  not the capture hot path.
- Director loop (C4D) consumes Asset-Understanding-settled semantic status, not an
  inline guess — removing the "model overwrites BeatProgress" risk entirely.
- No production camera changes, no Asset Understanding build, no contract edits in
  this audit.

**STOP. Awaiting the go/no-go decision.**
