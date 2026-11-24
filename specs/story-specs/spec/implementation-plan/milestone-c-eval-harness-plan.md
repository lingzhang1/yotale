# Milestone C — Evaluation Harness: Implementation Plan

**Status:** Deterministic foundation BUILT + wired to CI; model-dependent layers
planned. **No real AI.**
**Date:** 2026-10-01
**Companion to:** `13-evaluation.md` (the LIVING evaluation spec). This doc is the
**operational** plan: fixture format, runner, deterministic validators, result
persistence/comparison, and where it all lives. The harness is in place BEFORE
real models so every prompt/model change is measurable, not judged by demo feel.

---

## 0. Why now, and what's already done

`13-evaluation.md` is a **living specification** — it is never "closed." Every bad
Director behavior found in dev or the field becomes a regression fixture (§25).
Accordingly the harness is built to make adding fixtures cheap.

**Built this task (Layer 0 — deterministic, zero model cost, runs in CI):**
`evals/harness/` with fixture loader, deterministic validators, runner, result
record + run comparison, and self-tests. Wired into `pytest` (`testpaths` now
include `evals/harness`). **57 tests pass** (49 contract + 8 harness).

**Planned (Layers 1-3 — require a real model):** scaffolded as interfaces, filled
when models are turned on.

---

## 1. Where it lives in the repo

```
evals/
├── harness/                      # the runnable harness (Python package)
│   ├── __init__.py               # scope + layer doc
│   ├── fixtures.py               # Fixture dataclass + loader (*.fixture.json)
│   ├── deterministic.py          # Layer-0 checks (no model)
│   ├── runner.py                 # run + RunRecord + compare_runs (regression)
│   ├── test_harness.py           # self-tests (prove the harness works)
│   ├── judge.py                  # [planned] LLM-judge adapter via Model Gateway
│   └── contrastive.py            # [planned] scene/intent divergence scoring
│
├── creative_intent/              # fixtures: *.fixture.json
├── scene_understanding/
├── story_director/               # director_tmb_scale_001, edge-regression (seeded)
├── end_to_end/
└── results/                      # persisted RunRecord JSON (gitignored or kept)
```

Fixtures live under `evals/<component>/**.fixture.json`; the harness is a package
under `evals/harness/`. Pytest resolves `evals.harness` because conftest puts the
repo root on `sys.path` (same mechanism as `contracts`).

---

## 2. Fixture format (stable, §23-24)

JSON, one case per file, stable `id`, no pinned prose (we evaluate semantic
behavior). Shape (implemented in `fixtures.py`):

```json
{
  "id": "director_tmb_scale_001",
  "component": "creative_intent | scene_understanding | story_director | end_to_end",
  "phase": "initialize | next | contrastive_scene | contrastive_intent | loop | ...",
  "inputs": { "creative_intent": {...}, "scene_understanding": {...},
              "capture_constraints": {...}, "prior_director_state": {...},
              "latest_validation": {...} },
  "expected_properties": [ "uses mountain/person scale contrast" ],
  "forbidden_properties": [ "walking backward near edge" ],
  "expected_decision_action": "capture_shot",
  "failure_labels": [ "GENERIC_DIRECTION" ],
  "contrast_group": "tmb_intent_axis",
  "tags": [ "regression", "safety" ]
}
```

- `expected`/`forbidden_properties` are natural-language — read by the LLM-judge
  and human layers; the deterministic layer only acts on the subset that maps to
  hard machine rules (safety keywords, referential integrity).
- **Contrastive sets** (§10-12) share a `contrast_group` and vary exactly one
  axis (intent OR scene); `contrastive.py` (planned) compares their outputs for
  material divergence.
- `failure_labels` use the taxonomy (§26) so results are actionable.

---

## 3. Runner & layers

| Layer | What | Model? | Status |
|---|---|---|---|
| **0 — contract/deterministic** (§4, §19) | schema valid, every `shot.beat_id` exists, every shot serves a beat, `capture_shot`/`retry_shot` carry a shot, `create_now`/`rescan_scene` don't, valid enums, id uniqueness, hard safety-keyword flags | **No** | **BUILT** |
| **1 — component quality** (§5-6) | intent fidelity, scene grounding/hallucination, Director-relevance, compactness | Yes (LLM judge + human) | planned |
| **2 — Director behavior** (§8-14) | the 0/1/2 rubric; scene-specificity + intent-sensitivity contrastive matrices; loop adaptation (retry vs new shot vs create_now) | Yes | planned |
| **3 — end-to-end / field** (§20-22) | real-device sessions, finished-Story value, "would you have thought to shoot it this way?" | Real devices + humans | planned |

The runner (`runner.py`) takes a `(Fixture, candidate_output)` pair. Today
`candidate_output` is supplied by the caller (canned, or test-constructed); once
real engines exist, it is the engine's live output through the Model Gateway —
the harness interface does not change.

### Deterministic checks (built, `deterministic.py`)
`run_deterministic_checks(component, payload)` →
- `creative_intent` / `scene_understanding`: `schema_valid` (frozen contract,
  `extra="forbid"`).
- `story_director`: validate the `{story_plan?, decision}` envelope +
  referential integrity (orphan beat ids, beatless shots), decision/shot
  coherence, and conservative hard-safety instruction flags.

Heuristics FLAG for review; they never define creative failure unless the
constraint is truly hard (safety) — per §19.

---

## 4. Result persistence & comparison (§25, §27)

`runner.py`:
- `FixtureResult` — per-fixture pass + per-check detail.
- `RunRecord` — a run with provenance for experiment tracking (§27):
  `model`, `provider`, `prompt_version`, `schema_version`,
  `fixture_set_version`, `created_at`. `save()` writes `evals/results/<run_id>.json`.
- `compare_runs(baseline, candidate)` → `{regressions, fixes, added}`. A
  **regression** = a (fixture, check) that passed in baseline and fails now. This
  is the gate that keeps the regression suite (§25) meaningful across prompt/model
  iterations.

---

## 5. Regression workflow (makes 13-evaluation.md "living")

1. A bad behavior is found (dev or field) → write a `*.fixture.json` under the
   right component with `tags:["regression"]` and the right `failure_labels`.
2. If it's a hard, machine-checkable property (unsafe phrasing, broken
   reference), add/extend a deterministic check so it fails in CI immediately.
3. If it's a quality property, it's caught by the Layer-1/2 judge+human rubric
   once models are on.
4. `compare_runs` ensures a future prompt/model change that reintroduces it shows
   up as a **regression**.

The seeded `mountain_edge_backward_motion_regression.fixture.json` is the first
such case (the §25 cliff/backward-motion example).

---

## 6. Planned model-dependent pieces (fill when models are on)

- `judge.py` — an LLM-judge adapter that goes through the **generic Model
  Gateway** (same seam as the engines), receives source intent/scene + Director
  output + the explicit rubric (§18), and returns per-dimension 0/1/2 scores.
  Calibrated periodically against human review (§2.5, §18).
- `contrastive.py` — scene-sensitivity (§10) and intent-sensitivity (§11)
  divergence: run a `contrast_group`, assert outputs differ materially on the
  varied axis. This is the top Director gate (both axes).
- Pairwise comparison recorder (§17) and human-review store (§16) — small JSON
  schemas for blinded A/B reasons; no model, but model-produced inputs.
- Baselines (§15): generic-LLM, intent-only, no-beats — run through the same
  runner to prove the architecture earns its complexity.

---

## 7. Milestone-C quality gates (§29) — how the harness enforces them

**Hard gates (deterministic, enforced in CI now):** schema validity, referential
integrity, no known unsafe-direction regression, no fabricated plan on model
failure (the last checked once engines exist, via the retry/failure path).

**Quality gates (Layer 1-2, when models are on):** scene-specific in the majority
of curated cases; sensitivity to different intents; executable instructions; no
systematic wide/medium/close template; correct retry-vs-new-shot behavior; early
`create_now` where enough material exists.

---

## 8. Definition of Done — harness (maps to §33)

- [x] stable fixture format + loader (`fixtures.py`)
- [x] deterministic schema/referential/enum/safety checks run automatically in CI
- [x] result record with model/prompt/schema/fixture-set versions (`RunRecord`)
- [x] run comparison / regression detection (`compare_runs`)
- [x] regression fixtures can be added trivially (seeded one)
- [x] self-tests prove the harness works with zero model cost (8 tests)
- [ ] Creative Intent / Scene Understanding / Director fixtures fleshed out
      (seeded Director; expand as engines land)
- [ ] contrastive scene + intent runners (`contrastive.py`) — needs a model
- [ ] pairwise + human-review stores — needs model-produced outputs
- [ ] LLM-judge adapter (`judge.py`) — needs the Model Gateway live

The deterministic foundation is the prerequisite that must exist before real
models; it does. The remaining items attach to the same loader/runner/results
spine with no redesign.
