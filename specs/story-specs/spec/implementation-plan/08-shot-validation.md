# 08 — Shot Validation

> # ⛔ REJECTED FOR INLINE MVP IMPLEMENTATION (2026-10-05, approved)
> **The immediate/inline semantic Shot Validation described below is NOT the active MVP
> plan.** The GO/NO-GO audit (`milestone-c4-go-no-go-audit.md`), on evidence from
> `milestone-c4a-shot-validation-eval-report.md` and
> `milestone-c4a2-capture-evidence-report.md`, found that inline semantic validation does
> not earn its ~4–5s blocking latency, recurring inference cost, network dependency,
> complexity, or its trust-breaking false-GOT-IT failure mode (≤10s band: 0.61 user-state
> accuracy, 10/11 errors false GOT IT, one trust-breaking).
>
> **Active MVP plan = C4-LITE, a CAPTURE INTEGRITY checker** — see
> `milestone-c4-lite-capture-integrity-design.md`. C4-Lite is local-only (no AI / no AWS /
> no Bedrock / no network), makes **negative** claims ONLY for high-confidence obvious
> integrity failures, and otherwise says neutral **"Saved" / "Moment added"** — it NEVER
> claims the requested Shot/Beat was fulfilled, semantic success, or Story utility.
>
> **The entire semantic design in this file (three states GOT IT / KEEP + ONE MORE / TRY
> AGAIN, 4-axis judgment, purpose-conditioned VLM, derivation) is PRESERVED BELOW as
> rationale/research for the future asynchronous Asset Understanding**, where the semantic
> Shot/Beat/execution/story-utility judgment moves. Do not implement it inline. Nothing
> below this banner describes the active MVP.
>
> ---

## Overview (HISTORICAL — semantic design, moved to async Asset Understanding)

After each captured clip, quickly check whether it accomplishes the creative purpose for
which the Shot was requested — **not** whether the user literally obeyed the instruction.
Shows while the user is standing there; must be fast and lenient.

> **C4 corpus-driven correction (2026-10-04, approved).** The original surface here was a
> binary **PASS / RETRY**. Building the real evaluation corpus (`evals/assets/videos/`, 66
> clips across 10 categories incl. the A01 semantic-adversarial set) showed a binary verdict
> cannot express the common, important case of **good footage that does NOT fulfill the
> requested Shot but is still worth keeping**. The user-facing surface is therefore now
> **three** concise, non-technical states. The internal judgment, derivations, Moment
> lifecycle and Director-loop integration are specified in
> `milestone-c4-shot-validation-design.md` (§3–§5). Scores/axes are never shown to the user.

**Three user-facing states:**
- **GOT IT** — the captured Moment fulfills or sufficiently contributes to the requested
  Shot (includes *alternative fulfillment*: a non-literal take that still achieves the
  shot's purpose, and *partial* contributions).
- **KEEP + ONE MORE** — the clip is useful Story material and is retained, but it does not
  fulfill the requested Shot/Beat sufficiently. The user understands: *"We'll keep this, but
  let's get one more for what we're missing."*
- **TRY AGAIN** — the capture is technically unusable, OR it provides neither
  requested-purpose fulfillment nor useful Story value.

Still **lenient-biased**: when genuinely uncertain between GOT IT and KEEP + ONE MORE,
prefer the more positive state; a false TRY AGAIN (making a user retake a fine clip) is the
worst outcome. Retake is always optional — the user may proceed regardless of the state.

---

## Requirements

- **Three semantic states only** (GOT IT / KEEP + ONE MORE / TRY AGAIN) — no scores,
  percentages, or quality ratings shown to the user.
- Purpose-conditioned: judge against the Shot's **purpose** (why it was requested) and the
  Beat it serves, not literal instruction-following. A deviated-but-purposeful take is GOT IT.
- **Semantic contradiction is not a pass:** footage that means the *opposite* of the
  requested purpose (e.g. requested "departure", captured "arrival/sitting down") leaves the
  requested Shot **unfulfilled** → KEEP + ONE MORE if the footage still has Story value, else
  TRY AGAIN.
- Gross-failure technical checks still apply: clip long enough, subject visible, no
  catastrophic obstruction, camera reasonably stable, not severely out of focus, expected
  motion roughly occurred. A gross technical failure is TRY AGAIN.
- The KEEP + ONE MORE / TRY AGAIN reason is one plain-language sentence:
  "Lovely clip, but we still need the departure moment." / "Someone walked in front of you
  halfway through." Not "subject occlusion at t=2.3s."
- Latency: < 3 seconds from clip capture completing.
- **Lenient-biased:** when uncertain, prefer the more positive state. Edit Planner handles
  minor quality issues.
- Retake is always optional; the user can proceed regardless of verdict.

---

## Design

**Pipeline:**
```
Captured clip + Shot (purpose, instruction, subject_action, camera_motion) + Beat.purpose
        ↓
Duration check (AVFoundation): clip ≥ shot.duration × 0.7?
  +
Motion energy heuristic: catastrophically unstable? / severely out of focus?
  +
Ordered, timestamped frame sequence (device-decoded; handles HEVC + portrait/landscape;
  see c4 design §7 — supersedes the old 3-still sampler, needed for temporal cases)
        ↓
VLM call → internal ShotValidationJudgment (4 axes; c4 design §3.1)
        ↓
deterministic derivation → GOT IT | KEEP + ONE MORE | TRY AGAIN  (+ reason)
```

**VLM prompt (shape):** "You are reviewing a captured video clip, in order over time. The
shot's PURPOSE is: [purpose]. The user was told: [instruction]. It serves this story beat:
[beat.purpose]. Judge whether the footage ACCOMPLISHES THE PURPOSE — a different but
purposeful execution still counts. Watch what happens first/then/last; note if the action
means the OPPOSITE of the purpose. Return the four axes (technical_usability,
execution_match, shot_purpose, story_utility). Be lenient on execution; be honest about
whether the purpose was met."

**UX:**
```
"Got it." (immediate feedback)
  ↓
Brief spinner (< 3 sec)
  ↓
✓ "Nice."                 ↺ "Keep this — one more for X."     ↺ "Let's try that again."
  (GOT IT)                   (KEEP + ONE MORE)                    (TRY AGAIN)
  ↓                           "Lovely, but we still need         "Someone walked in front
Next shot                      the departure."                     of you."
                              [Keep + continue] [Try again]      [Try again] [It's fine, continue]
```

---

## Tasks

**Phase 1 (fake):**
- [ ] Always return GOT IT after a 1-second fake delay
- [ ] Show "Nice." and proceed

**Phase 5 (real AI) — per `milestone-c4-shot-validation-design.md`:**
- [ ] Implement duration check + motion-energy / out-of-focus heuristic (deterministic Stage 1)
- [ ] Implement ordered, timestamped frame-sequence sampler (device-decoded; HEVC + both
      orientations; supersedes the old 3-still sampler — temporal cases need order)
- [ ] Design + test the purpose-conditioned VLM prompt → 4-axis `ShotValidationJudgment`
- [ ] Implement the deterministic derivation (axes → clip_disposition / requested_shot_status
      → GOT IT | KEEP + ONE MORE | TRY AGAIN)
- [ ] Tune leniency: measure false-TRY-AGAIN rate on the eval corpus; measure
      adversarial catch-rate on the A01 set; measure temporal accuracy on S02/S03/S05
- [ ] Measure latency; must be < 3s
- [ ] Build the three-state UX with plain-language reason and optional retake / keep+continue
