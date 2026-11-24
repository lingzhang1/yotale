# EditPlan/2 — proposed experimental contract (NOT frozen)

Status: PROPOSAL from the M-d.3 experiment. Extends the frozen `EditPlanContract` in
`contracts/schemas/ai_contracts.py` additively. Freeze only after the two M-d.3 §15 tweaks (duration discipline +
alignment restraint) and one confirming re-run, with owner approval. Every added field names a real consumer.

## Rationale
The frozen `EditPlanContract` keys off `creative_intent_id` only and predates E2/M-b/M-c: it cannot express which
Story/MusicPlan a plan belongs to, cannot link the chosen track's observed structure, and — most importantly —
has **no native-audio field**, contradicting the M-b first-class native-audio decision. The M-d.3 experiment
(5 scenarios, 10 Opus plans, 10/10 executable) exercised the shape below and confirmed native-audio and
segment-level alignment are load-bearing while a global `beat_sync` bool is redundant.

## Proposed shape (edit_plan/2)
```
EditPlanContract (edit_plan/2):
  id: UUID
  story_id: UUID                      # ADD — the plan belongs to a Story (consumer: persistence, cache keying)
  creative_intent_id: UUID            # KEEP
  target_duration_seconds: float>0    # KEEP — output pinned to the STORY target, not the track length
  output_format: OutputFormat         # KEEP
  music_asset_id: str | None          # KEEP — chosen real track (Epidemic UUID or story_catalog id)
  music_plan_id: UUID | None          # ADD — provenance (consumer: which MusicPlan shaped this; staleness)
  music_analysis_ref: ... | None      # ADD — the observed track structure the plan aligned to (by value or
                                      #        handle; NOT a cached mirror of provider metadata — see no-cache policy)
  segments: list[EditSegmentContract]
  created_at: datetime

EditSegmentContract (edit_plan/2):
  order: int>=0                        # KEEP (monotonic, unique)
  asset_id: UUID                       # KEEP — MUST be an existing Moment id; never invented
  source_start_seconds: float|None     # KEEP — within Moment duration AND useful_segments
  source_end_seconds: float|None       # KEEP
  output_duration_seconds: float>0     # KEEP
  crop: CropInstruction | None         # KEEP
  speed: float|None                    # KEEP
  transition: TransitionInstruction|None # KEEP
  narrative_role: str | None           # KEEP (free-text MVP; may later reference a StoryGuide dimension id)
  native_audio: NativeAudioIntent      # ADD, REQUIRED — keep | duck | mute (consumer: Media Engine audio mix).
                                      #   realizes MusicPlan.audio_strategy per segment. INTENT only, no curves.
  music_alignment: MusicAlignment|None # ADD — {anchor: beat|downbeat|highlight|none, note?}. SEGMENT-LEVEL.
                                      #   consumer: Media Engine cut placement. default none. NO global beat_sync.
```

New enums/models: `NativeAudioIntent{keep,duck,mute}`, `MusicAlignmentAnchor{beat,downbeat,highlight,none}`,
`MusicAlignment{anchor, note?}`. Reuse existing `CropInstruction`, `TransitionInstruction`, `TransitionType`,
`OutputFormat`.

## Decisions baked in (from the experiment)
- **No global `beat_sync` boolean.** Alignment is per-segment and heterogeneous (TMB-B: 6 downbeat + 1 highlight +
  1 none); a bool is lossy and redundant. Media Engine does the exact snapping from the per-segment anchor + real
  MusicAnalysis times.
- **`native_audio` is REQUIRED per segment** (not optional) — the planner must always declare the mix intent;
  the experiment showed it reliably protects the guitar performance / skate landing / solitude room tone.
- **`music_alignment` default `none`** — alignment is optional and narrative-first; anchors only where a beat/
  downbeat/highlight genuinely serves the Story (avoids the minimal_solitude over-alignment).
- **No model-authored mix curves / multi-track audio / explicit payoff marker** — Media Engine territory; the
  `highlight` anchor already encodes payoff placement.
- **Output duration tracks the Story target** (±20%), never the track length (guitar-B drift lesson).

## Executability contract (deterministic, model never self-certifies)
A validator enforces, before the plan reaches the Media Engine: every `asset_id` exists as a Moment; source
in/out within Moment duration and overlapping a `useful_segment`; positive output durations; monotonic unique
`order`; total within ±20% of target; `native_audio` present and valid; `music_alignment` anchor set only when a
MusicAnalysis is present. (Implemented + self-tested in `evals/edit_planner/`.)

## NOT frozen here
This is the experiment-validated proposal. Apply the M-d.3 §15 tweaks, re-run the 5 scenarios once, get owner
sign-off, THEN add these to `ai_contracts.py` + regenerate the JSON Schema + add contract tests as `edit_plan/2`.
