# Creative Editing V2-a — Phase 0 analysis (revised owner direction)

Status: 🔵 design/feasibility only — NO production implementation. STOP for owner review before any V2-b build.
Date: 2026-10-11. No code changed. Frozen EditPlan/2 + Edit Planner v4 untouched. Not pushed.

> Scope guard: this is Phase 0 (context recovery, evaluation, proposals, STOP gates) under the revised
> direction. It does not implement effects, does not reopen frozen contracts, and treats P1/Experimental
> items as HYPOTHESES to validate, not commitments.

---

## 1. Verified current roadmap status
- Creative Editing V2 was **recorded as a backlog, never started** (`milestone-rb-closure-rc-design.md` §11):
  "match cuts · motion continuity · speed ramps · sound bridges · color matching · layered compositions ·
  split screens · masking → all require the separate Edit Evidence experiment (R-a design). AU/Edit-Planner
  contracts NOT reopened." There is **no prior committed V2-a roadmap doc** in the implementation plan — this
  is the first V2-a design artifact. (The "previously approved roadmap" lives only as the §11 backlog + the
  R-a Edit Evidence idea.)
- Live today: Edit Planner **v4** (frozen, narrative significance-weighting), EditPlan/2 (frozen), **Media
  Engine V1** on device.
- **Renderer V1 capabilities that already exist** (so some Level-2 *primitives* are present, under-used):
  - straight **cut**; **dissolve** = real 0.3s crossfade (two video tracks, opacity ramp); **fade** (single-clip).
  - **speed** 0.5x/2x via `scaleTimeRange` (DEBUG-exercised, not planner-driven).
  - per-segment **native-audio** keep/duck/mute with click-guarded ramps.
  - **No**: match-cut logic, sound bridges (audio leading/trailing across a cut), color/exposure continuity,
    any layering/compositing.

## 2. Current V1 quality weaknesses (honest, from the first real renders + guitar audit)
Observed cause of "feels basic" is **NOT missing advanced transitions**. Ranked by impact:
1. **Imprecise cut boundaries (P0).** Segments use AU `useful_segments` ranges, not *action-aware* in/out
   points — cuts land mid-gesture (mid-strum, mid-step) rather than on a motion/beat boundary.
2. **Pacing uniformity (timing).** Segment durations are allocation-driven, not rhythm/energy-driven; the cut
   cadence is even where the footage wants acceleration/held beats.
3. **Audio discontinuity (P0).** Each segment's native audio starts/stops at its own cut (ramped) — no sound
   bridge, so continuous actions (a guitar phrase) are chopped audibly.
4. **Narrative selection** is actually a **relative strength** (coherent 3-shot arc on guitar) — not the main gap.
5. **Visual discontinuity** (jump between similar framings) — secondary; real but less than 1–3.
6. **Missing cinematic transitions** — LAST, not first. Adding match cuts to badly-chosen boundaries would not fix 1–3.
7. **Unnecessary effects** — none present today (straight cuts); the risk is ADDING them without evidence.

**Conclusion:** the quality ceiling today is set by **cut-boundary precision + audio continuity**, not by a lack
of split-screens. Fix P0 first; most "cinematic" feel comes from *where* and *how* cuts land, not from effects.

## 3. Prioritized creative-editing capabilities (as hypotheses)
- **P0** — accurate cut-boundary selection; audio continuity + sound bridges.
- **P1** — motion-aware match cuts; selective speed ramps; color/exposure continuity.
- **Experimental** — split-screen; PiP; simple layered compositing (bounded feasibility only, §7).
- **Defer** — complex masking; animated effects; generative video; full timeline editor.
- A **clean straight cut is a valid winning output**; no capability is a predetermined requirement.

## 4. Minimal Edit Evidence proposal (every field named + consumer + benefit; deterministic, on-device)
AU today gives narrative evidence only (events/subjects/summary/useful_segments/temporal_order) — **no kinetic
or continuity signal.** Rather than raising every Moment's frame density, compute **targeted** evidence ONLY at
candidate cut boundaries + significant-action timestamps (from AU events), on-device, deterministic:

| Field | How (deterministic, on-device) | Consumer | Editing benefit |
|---|---|---|---|
| `motion_magnitude[t]` (coarse) | frame-diff / optical-flow magnitude at boundary ±0.5s | cut-boundary + match-cut | cut on motion settle; match outgoing↔incoming motion |
| `motion_direction` (L/R/up/down/none) | flow dominant vector | match cut | continuity of movement across a cut |
| `subject_bbox` + `scale` at in/out | Vision person/face/saliency box | match cut, entrance/exit | match subject position/scale; avoid jarring jumps |
| `exposure_mean` + `white_balance` at in/out | avg luma + simple WB estimate | color continuity (P1) | flag/soft-correct exposure jumps across a cut |
| `audio_rms[t]` + `onset` near boundary | on-device audio envelope | sound bridge, audio continuity | choose J/L-cut points; avoid chopping a phrase |
| `action_peak_t` | AU event start/end already present | cut timing | land cuts relative to the action, not mid-gesture |

Rules honored: deterministic on-device preferred; NO whole-video / all-frames to an LLM; NO blanket density
increase; each field has a named consumer + benefit. This is a **proposal**, not a contract yet (see §8).

## 5. Single enriched planner (A) vs narrative planner + creative refinement stage (B)
- **A — enriched single Edit Planner:** feed Edit Evidence into v4's input → one model call emits narrative +
  transition/speed/bridge decisions. Pros: one call, no new orchestration. Cons: reopens the frozen v4 prompt;
  mixes two very different decision types (narrative selection vs visual transition) in one inference → harder
  to evaluate/attribute quality; higher regression risk to the proven narrative behavior.
- **B — narrative planner (frozen v4) → targeted Creative Edit refinement stage:** keep v4 producing the
  narrative EditPlan/2 unchanged; a SECOND, bounded stage consumes the plan + Edit Evidence and emits only the
  *visual/audio refinement* decisions (cut-boundary nudge, transition choice, speed ramp, bridge). Pros:
  frozen contracts/prompt preserved; separable + independently evaluable; the refinement can be **deterministic
  first** (no 2nd model call) and only escalate to a model if determinism underperforms. Cons: a second stage.
- **Do NOT assume two model calls are necessary.** Recommendation: **B, with the refinement stage DETERMINISTIC
  by default** (evidence-driven boundary snap + transition/bridge rules), measured against A only if determinism
  loses. This directly satisfies "prefer B only if separation improves quality/reliability" — and separation
  here is primarily about *protecting the frozen narrative planner*, which is a reliability win regardless.

## 6. Real-footage quality experiment design
- **Footage on disk:** `evals/scenarios/guitar_practice_001/` has **6 real clips** (string_first_touch,
  guitar_overview, first_practicing_a_song, first_song_but_not_familar, familar_with_song, final_song).
  **CORRECTION (V2-b Phase 0):** an earlier draft of this doc said "5" — it is **6**; the AU audit covers all 6.
- **The `editorial_reference.APPROVED.json` is a human-APPROVED NARRATIVE ANNOTATION, not a rendered human
  edit.** Its own provenance states `annotations_in_dir: "none"` and its durations are explicitly "editorial
  CANDIDATES, not model instructions or scoring thresholds" — there is NO cut-timing EDL and NO rendered video.
  So it is a narrative-expectation checklist, NOT a Phase-5 "C" baseline. **There is no genuine human-edited
  reference** for guitar; the experiment is **A/B only**, with this annotation used to sanity-check narrative
  coverage. TMB is reference-pointers (A/B only). **San Francisco footage is NOT present** (deferred per owner).
- **Conditions, same source + CreativeIntent:** A = current V1 edit; B = evidence-informed V2 (deterministic
  refinement per §5-B). **C (rendered human reference) does not exist** — not fabricated.
- **Score (blind where possible):** narrative coherence · pacing · cut quality · visual continuity ·
  native-audio continuity · emotional effect · artifacts · viewer preference. **A clean straight cut wins if it
  wins** — effects earn nothing for merely existing.
- Output: a scorecard + the 2–3 rendered variants per scenario for owner listening/viewing.

## 7. Layered-editing feasibility (bounded — NO compositing engine)
- **Scenario with genuine value:** guitar **"early vs later practice"** split-screen — `first_practicing_a_song`
  (left) vs `familar_with_song`/`final_song` (right) showing progress simultaneously. This is the rare case
  where simultaneous perspectives add narrative meaning (improvement over time), not decoration.
- **Technical feasibility:** the renderer already uses **two video tracks** (for crossfade). A static 50/50
  split is a bounded extension: two `AVMutableVideoCompositionLayerInstruction`s with side-by-side transforms,
  no masking/animation. Feasible as a one-off; NOT a general compositing engine.
- **Visual quality risk:** portrait source + side-by-side → heavy cropping; may need a vertical stack instead.
  Evidence need: subject bbox (from §4) to keep both subjects framed.
- **Contract implication:** EditPlan/2 has no multi-layer concept → would need a **versioned extension**
  (EditPlan/3 or a `layers` addition), NOT a reinterpretation of existing fields. Defer unless the experiment
  shows the split meaningfully beats two sequential clips.

## 8. Contract implications
- **Preserve frozen EditPlan/2 + Edit Planner v4** throughout the experiment. The deterministic §5-B refinement
  stage needs **no contract change** if it emits renderer-level directives consumed by the Media Engine, not by
  re-encoding EditPlan/2.
- If a validated capability needs new plan fields (e.g. per-segment `cut_in/out_nudge`, `sound_bridge`,
  `speed_ramp`, or `layers`), propose a **versioned EditPlan/3** — never silently reinterpret EditPlan/2 fields.
  `TransitionType` already has `cut|fade|dissolve`; speed/bridge/layers are NOT expressible today.
- Edit Evidence itself, if persisted, is a **new sidecar contract** (not part of MomentUnderstanding) so AU
  stays frozen and density unchanged.

## 9. Cost & latency estimates (Phase-0, to be measured)
- Edit Evidence (deterministic, on-device, boundary-only): no model call; CPU/Vision cost bounded to a handful
  of frames per candidate boundary (≈ segments×2 boundaries × few frames) — target < ~1–2 s added on device,
  to be measured, NOT a model/token cost.
- §5-B deterministic refinement: zero model calls. If a model refinement is later tested, it is ONE extra call
  on a compact evidence payload (no video/frames to the LLM) — bounded like the existing planner call.
- Rendering: split-screen/speed reuse existing AVFoundation paths; render-time increase bounded, to be measured.

## 10. Proposed V2-b implementation scope (for owner approval — NOT started)
Smallest slice that tests the real hypothesis (P0 first):
1. Deterministic **Edit Evidence** at candidate boundaries (motion + audio onset + action_peak) — on device.
2. Deterministic **cut-boundary refinement** (snap in/out to motion-settle / audio-onset) — no contract change.
3. Deterministic **sound bridge** (J/L cut) on continuous-audio segments — renderer directive.
4. Run the §6 A/B/C experiment on guitar (+TMB A/B). Decide P1/Experimental ONLY on evidence.
Explicitly OUT of V2-b: split-screen/PiP (feasibility only), color pipeline, any model refinement, EditPlan/3.

## 11. Explicit owner decisions needed
1. Confirm **P0-first** framing (cut-boundary + audio continuity) over "add transitions" — AGREE / adjust.
2. Approve architecture **B (deterministic refinement stage, frozen v4 preserved)** vs A (enriched planner).
3. Approve the **minimal Edit Evidence** field set (§4) — any field to drop/add before any build.
4. Provide **San Francisco footage** (absent) or confirm the experiment runs on guitar+TMB only.
5. Approve the **V2-b scope** (§10) as the next build slice, or re-scope.
6. Split-screen: feasibility assessment only now (§7) — confirm NOT implementing in V2-b.

STOP for owner review. No implementation, no contract change, nothing pushed.
