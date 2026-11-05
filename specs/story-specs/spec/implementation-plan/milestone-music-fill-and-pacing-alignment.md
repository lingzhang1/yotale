# Milestone — Music-Fill Correctness + Music-Aware Editorial Pacing (design)

Status: **Music-fill IMPLEMENTED + unit-tested; awaiting physical-device acceptance. Pacing-alignment is a
DESIGN + bounded experiment only (no production implementation, no frozen-prompt/contract changes).**

## PART 1 — Music-fill correctness (DONE in code, device gate pending)

### The bug
`MediaEngineV1.buildComposition` inserted the soundtrack ONCE for `min(trackLen, videoLen)`. A ~120s track on
a 200s+ Story left **120–200s silent** ("half the video has no music"). The prompt's "music is cut/looped
downstream" was never implemented in the renderer.

### The fix (commit 8b65b7f, NOT pushed)
- New pure `SoundtrackLoopPlan.compute(trackSeconds, totalSeconds, seamSeconds)` returns the loop iterations
  (track index, start, length) + seam times, or `nil` for an unusable asset. Video length is authoritative.
- `buildComposition` lays loops onto TWO alternating audio tracks so each loop's tail can crossfade into the
  next loop's head (0.4s seam crossfade). `buildAudioMix` ramps each seam (outgoing 1→0, incoming 0→1) and
  applies a 1.0s final fade-out at the video end.
- Preserved: user Story duration (never capped to music); native-audio keep/duck/mute; Immersive/Balanced/
  Music-led gains (`soundtrackGainUnder`); intentionally music-free passages (keep+important+sparse → music
  gain 0, so a seam/fade ramp there is a no-op); EditPlan/2, cuts, visual composition all untouched.
- Safety: track < 0.5s, zero, NaN, infinite, trackless, or zero-length timeline → `nil` → native-audio-only
  render (no runaway loop, no divide-by-zero). Runaway guard at 10k iterations.
- Observability: render beacon now reports `loops=N seams=M total=Ts` to the App Runner access log.

### Renderer tests (deterministic, 8 new in MediaEngineV1Tests)
Verified standalone (sandbox can't run XCTest): loop count, seam count/placement, FULL coverage to `total`
(no silent tail), track-longer-than-video single truncated loop, short-track many loops ending exactly at
total, track alternation, seam-pullback never inverting, and the unusable-asset fallbacks. The fade/seam gain
contract asserts music-free passages stay silent and duck passages fade a real non-zero gain to 0.

### Physical-device listening checklist (owner acceptance — steps 3-4)
Render a **200s+ TMB Hiking** Story on a real iPhone and confirm:
1. [ ] Music plays through the ENTIRE video — no silent tail after ~2 min.
2. [ ] Loop seams are smooth — no click, pop, or abrupt restart at the ~120s / ~240s joins.
3. [ ] The track fades out gently at the very end (no hard cut to silence).
4. [ ] Native audio still reads correctly — kept moments (performance, speech, ambience) are audible; ducked
       moments sit under the music; muted moments are silent.
5. [ ] Immersive vs Balanced vs Music-led still behaves as before (music-led = music forward; immersive = real
       sound forward).
6. [ ] A deliberately music-free / native-led stretch is NOT overridden by the loop.
7. [ ] Visuals/cuts are IDENTICAL to before (fix is audio-only).
8. [ ] Beacon in App Runner access log shows `loops>=2 seams>=1` for the long render.

## PART 2 — Music-aware editorial pacing (DESIGN + bounded experiment; NOT production)

### Existing MusicAnalysis limitations (what we have today)
- `MusicAnalysisV1`: `durationSeconds, bpm, tempoReliable, beats[], downbeats[], highlightWindow`. The device
  MCP/REST provider path populates `energy_curve` from a waveform (BBC JSON) in MCP mode; beats/downbeats/
  highlight are HONESTLY EMPTY unless the provider supplies them (never inferred from bpm).
- Alignment today is ONE-DIRECTIONAL and renderer-side only: `snappedCut` nudges an already-chosen planner cut
  to the nearest beat/downbeat ONLY when `anchor != none` AND `tempoReliable`. Ambient (tempo not reliable) is
  never snapped. The planner reasons about music via the prompt but the renderer never matches CONTENT energy
  to MUSIC energy.
- Separately, `CreativeRefinementV2b` nudges cut placement toward motion-settled / audio-onset points from the
  video — but independently of the music. **Nothing matches video pacing to music pacing.**

### Experiment: narrative-first vs music-informed-narrative-first
- Arm A (control): current narrative-first Edit Planner + existing refinement.
- Arm B (candidate): narrative-first planning INFORMED by real music structure + energy evidence —
  shot-duration variation guided by music energy progression; major cuts/payoffs biased toward RELIABLE
  musical transitions/climaxes; rhythm alignment ONLY where reliable evidence exists.

### Evaluate (per fixture: Hiking, Girl-with-Dress, Guitar, Solitude)
shot-duration variation; music energy progression; visual action/movement; musical transitions & climaxes;
narrative payoffs; native-audio continuity; continuous-action preservation; rhythm alignment where reliable.

### Guardrails (owner)
Do NOT force cuts onto every beat. Do NOT infer reliable beats from BPM alone. Do NOT treat waveform amplitude
as emotional intensity (energy ≠ emotion). Do NOT alter frozen prompts or contracts during the experiment —
the experiment reads/augments evidence out-of-band and measures, it does not re-freeze anything.

### Additional audio-analysis requirements (likely)
Reliable musical structure (section boundaries, verified downbeats, a trustworthy climax window) is NOT
guaranteed by the current provider payload. A real music-aware pacing feature would likely need a dedicated
music-structure analysis (onset/beat tracking with a reliability flag, section segmentation) — a provider or
on-device capability that does not exist yet. The experiment should quantify how often reliable evidence is
actually present before committing to build on it.

## Cost & latency
- Music-fill: zero model cost (pure renderer change). Negligible added render time (extra audio-track inserts).
- Pacing experiment: a handful of edit-plan calls per fixture, well within the $20 model-spend gate.

## Recommendation for the next editing-quality milestone
Ship the music-fill fix after device acceptance. For pacing, run the bounded A/B first and gate any production
work on whether reliable music-structure evidence is present often enough to matter — do not build music-aware
pacing on BPM-only or amplitude-as-emotion signals. STOP for owner review before any creative-planning change.
