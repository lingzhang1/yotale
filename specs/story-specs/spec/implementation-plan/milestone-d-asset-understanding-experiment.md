# Asset Understanding — intelligence/transport experiment (report)

Status: **EXPERIMENT COMPLETE — report only. NOT ready to freeze the design (one gap, §19/§20).
No production Asset Understanding built. No canonical contract modified. No async infra built.
No Music/Edit Planner.**
Date: 2026-10-05. 26-clip subset × 5 arms, live Bedrock (acct 989088054552, us-east-1).
Runner `evals/run_asset_understanding.py`; subset `evals/asset_understanding/subset.json`;
raw `evals/results/asset_understanding_exp.json` (gitignored).

The question: *what evidence representation lets a model understand an entire Moment well
enough for Story?* Native whole-video was the hypothesis to beat.

---

## 1. Evaluation subset (exact)

26 clips from the private C4 corpus (no new data): **10 short (≤10s) / 7 medium (10–30s) /
6 long (>30s, incl. 95s + 154s)**. Coverage: temporal (departure/arrival, reveal direction,
progression, contradiction), semantic (difficulty, companionship, end-of-day,
alternative-success, beautiful-but-wrong-purpose), multi-event, technical/dead-footage, and a
shared-source pair (A01↔A06). Full list in `subset.json`.

## 2. Experimental AU schema (NOT canonical)

`summary · subjects[] · environment · events[{t_start_s,t_end_s,description}] ·
temporal_order_note · useful_segments[{t_start,t_end,why_useful}] ·
dead_or_setup_segments[] · story_utility{none|useful_elsewhere|strong_elsewhere} ·
requested_shot_contribution? · requested_beat_contribution?`. Observed events stay grounded
in the video; Story-contribution fields only when capture_context is present. This asks "what
useful Story material exists?", not "how to edit".

## 3–4. Approaches × models tested

| arm | representation | model | native? |
|---|---|---|---|
| ft_nova_pro | frame-timeline (duration-scaled 6–24 ordered frames) | amazon.nova-pro-v1:0 | no |
| ft_sonnet | frame-timeline | us.anthropic.claude-sonnet-4-6 | no |
| nv_nova_pro | **native video** (Converse S3-source) | amazon.nova-pro-v1:0 | yes |
| nv_nova_lite | **native video** | amazon.nova-lite-v1:0 | yes |
| nv_pegasus | **native video** (InvokeModel S3-source) | us.twelvelabs.pegasus-1-2-v1:0 | yes |

**Model discovery (verified, not assumed):** VIDEO-input models in-account = **Nova Pro/Lite
(ON_DEMAND)**, **Nova 2 Lite** (profile), **TwelveLabs Pegasus 1.2** + Marengo embeddings
(profiles). **Claude (Sonnet/Opus) do NOT accept native video** — image-only, so Claude can
only do frame-timeline. (Hierarchical analysis §C: frame-timeline Nova Pro already behaves as
a cheap coarse pass; a two-stage coarse→region pass is noted as a future option, not built —
single-pass whole-video/whole-timeline was sufficient on this corpus.)

## 4–11. Results (aggregate)

| arm | valid | lat p50 | lat p95 | events med | useful med | long p50 |
|---|---|---|---|---|---|---|
| **ft_nova_pro** | **26/26** | **5.2s** | 10.7s | 4 | 1.5 | 9.9s |
| ft_sonnet | 20/26 | 21.9s | 27.6s | **5** | **3** | 27.6s |
| nv_nova_pro | 25/26 | 8.5s | 14.4s | 4 | 2 | 11.4s |
| nv_nova_lite | 24/26 | 5.3s | 8.9s | 3 | 2 | 8.7s |
| nv_pegasus | 25/26 | 8.7s | 14.7s | 3 | 2 | 11.0s |

**7. Temporal quality.** No single model dominates. On the reverse-reveal clip, **ft_sonnet
and nv_pegasus** nailed direction ("landscape FIRST → person LAST, opposite of requested");
ft_nova_pro/nv_nova_pro got the ordering but less sharply. On arrival-vs-departure,
ft_nova_pro/ft_sonnet/nv_nova_pro correctly read "arrival/enters" — **Pegasus got it
backwards** ("person departing"). Frame-timeline (with timestamps) is **competitive with
native video** on temporal reasoning; it does not require native video to get ordering right.

**8. Segmentation.** ft_sonnet produced the richest useful_segments (median 3) when it
succeeded; native arms and ft_nova_pro produced usable 1–3 segments; all identified
dead/setup regions on the camera-points-away and sleepy clips. Boundaries are approximately
right, good enough as Edit-Planner candidate inputs (§EDIT-UTILITY passes qualitatively).

**9. Story-contribution.** All arms produced grounded `story_utility`; the shared-source
A01↔A06 pair received the same observed events but the capture_context shifted the
contribution judgment, as intended. ft_sonnet's prose was sharpest; Nova/Pegasus adequate.

**10. Latency/cost.** Native video is cheap in tokens (video tokenizes to ~2.3k for a short
clip, ~44k for 154s). Frame-timeline Nova Pro is the fastest reliable arm (p50 5.2s). Sonnet
is 4× slower and least reliable. No arm is expensive at this scale; cost is not the
discriminator (per instruction).

**11. Short/medium/long.** Short/medium: every arm fine. **Long is where arms diverge** (§12).

## 12. Video/input limits discovered (verified against the live API)

- **Converse direct bytes** (video.source.bytes): works for short clips; practical request
  cap ~25MB → unusable for medium/long. **S3 video-source is required** for anything bigger.
- **Converse S3-source** (video.source.s3Location + bucketOwner): works for Nova Pro/Lite;
  handled up to the 95s clip. **Both Nova arms FAILED the 154s/214MB clip** (native whole-video
  exceeded the model's effective video/token budget → empty/invalid output).
- **TwelveLabs Pegasus** (InvokeModel, native body `{inputPrompt, mediaSource.s3Location}`):
  **handled the 154s clip** (18.6s). But **rejected the 2.0s clip** with a ValidationException
  (too short / min-duration constraint). Does NOT support Converse.
- **Frame-timeline (any image model)** has **no clip-length ceiling** — it decodes locally to a
  bounded set of stills, so **ft_nova_pro was the ONLY Nova path that handled 154s**, and the
  only arm that handled every clip 2s→154s.
- Codec/orientation: HEVC + H.264, portrait + landscape all handled by every arm (device/S3
  decode is transparent).
- Measured native processing: short ~4–8s, medium ~8–14s, long(38–95s) ~11–24s, 154s ~19–43s.

## 13. App Runner timeout implications

Native-video model latency alone stayed **well under 120s** for every clip that succeeded
(max 42.7s, on the Nova 154s attempt that then failed on content). **But** the real
end-to-end budget for a production native path is: device→S3 upload (a 214MB clip took ~5s at
~45MB/s on a fast link, but mobile uplink is far slower — tens of seconds to minutes) **+**
model latency **+** result handling. On a cellular uplink a large Moment's upload alone can
approach or exceed 120s. **Conclusion: a synchronous App Runner request is a poor fit for the
native-video path** — not because inference is slow, but because mobile upload of whole video
is unbounded. Frame-timeline avoids this (frames are small), so a frame-timeline path *could*
fit synchronous App Runner, but Asset Understanding is explicitly async anyway.

## 14. Recommended async architecture

**C/B hybrid, NOT synchronous App Runner (A).** Asset Understanding is not user-blocking, and
the upload is the unbounded cost. Recommended shape (design only — NOT built):
- **App Runner stays the control plane** (enqueue job, read status/result) — reuse existing C1–C3
  infra, no migration.
- **Direct device→temporary-S3 upload** (presigned PUT), then an **async worker** picks up the
  job: frame-timeline for the common case, native-video (S3-source) for clips where native
  materially helps.
- **Queue + worker (D)** for durability/retry (iOS may background-suspend mid-upload). Bedrock
  async invocation is NOT required for the chosen models (Converse/InvokeModel are synchronous
  and fast enough once the bytes are in S3); the asynchrony we need is in OUR job lifecycle, not
  Bedrock's. (Pegasus/Nova have no async-invoke requirement at these durations.)

## 15. Temporary-media lifecycle recommendation

Confirmed viable: **local original (authoritative) → presigned temporary S3 upload → model
analysis → MomentUnderstanding persisted → temporary remote object deleted.** The experiment
bucket was private (public-access-block on), opaque keys, **1-day lifecycle**, and each clip was
**deleted immediately after analysis** in the run. Production should do the same: private
bucket, per-object delete on job completion + lifecycle backstop, no permanent cloud video.

## 16. Current iOS local-storage / Photos findings (inspected, unchanged)

From `apps/ios/Story/Story/Media/Playback/MediaStore.swift`:
- DIRECT captures persist at **`<App Documents>/media/<uuid>.mov`** (relative path stored so it
  survives relaunch; MediaStore is the only path↔URL mapper). Originals stay on device; nothing
  uploads.
- **Do Story captures appear in Apple Photos? NO.** They live only in the app's Documents
  container. The user will not see them in Photos.
- **Could deleting Story / the app lose the only copy? YES.** The Documents container is deleted
  with the app, and these files exist nowhere else → **Story is currently the only, invisible
  holder of the footage.** This is the trust risk called out in the brief.
- **Backup semantics:** the Documents directory is included in iCloud/iTunes device backup by
  default (not excluded), so a device backup would preserve them — but that is not the same as
  the user owning them in Photos, and is not guaranteed.

## 17. Recommended user-owned Photos persistence

**Recommendation: on capture (or on first successful save), ALSO save the original to Apple
Photos** via `PHPhotoLibrary` with `addOnly` permission, into a "Story" album.
- Rationale: the user owns and sees their travel footage outside Story; Story is never the sole
  invisible holder.
- **Duplicate-storage:** keep the Photos copy as the user-owned original and the Documents copy
  as Story's working copy (reliable to reopen/analyze without Photos permission prompts mid-flow).
  Accept the duplication for short clips; for large ones consider referencing the Photos asset
  (PHAsset localIdentifier) and dropping the working copy after analysis — a future design choice.
- **Delete semantics to design for:** user deletes the **Photos** copy → Story's working copy
  still analyzes (Story unaffected); user deletes the **Story** copy / app → the Photos copy
  remains the user's own (footage not lost). This is exactly the trust property wanted.
- Permission: request `addOnly` (write) not full library read; degrade gracefully if denied
  (keep working copy, inform the user Story is holding the only copy).
- **Not changed in this experiment** (brief says don't).

## 18. Recommended evidence/model architecture for Asset Understanding

- **Primary production path: frame-timeline on `amazon.nova-pro-v1:0`.** It was the ONLY arm
  valid on 100% of clips (2s→154s), fast (p50 5.2s), no clip-length ceiling, no upload of whole
  video required (small frames), competitive temporal/segmentation quality.
- **Native whole-video as a targeted enhancement, not the default.** It did NOT beat
  frame-timeline overall: native Nova failed the longest clip, and native quality was not
  consistently better. Keep **TwelveLabs Pegasus** as the native option for long clips where a
  dedicated video model's richer read is wanted (it handled 154s), but gate it on a **minimum
  duration** (it rejects very short clips).
- **Quality-ceiling reference: Sonnet 4.6 frame-timeline** — sharpest language, but 4× slower
  and 6/26 structural failures → unsuitable as the production default; useful only as an offline
  quality yardstick.
- So the hypothesis "native whole-video beats everything" **did not hold**: frame-timeline with
  a generous, duration-scaled, timestamped budget is the robust winner, with native video a
  per-clip enhancement.

## 19. Minimum additional eval annotations/data required (the gap)

This run measured validity/latency/richness and spot-checked temporal/segmentation
qualitatively, but there is **no ground-truth annotation** for AU yet (unlike C4's labeled
axes). To freeze the design we need, for ~15–20 of these clips:
- reference temporal orderings (for departure/arrival/reveal/progression/contradiction),
- reference useful-segment boundaries (approx start/end a human editor would pick),
- reference multi-event lists (for recall on the 95s/154s clips),
- reference story_utility per capture_context.
Then re-score the two finalist arms (frame-timeline Nova Pro, native Pegasus-for-long) against
it. Also: a few **catastrophic-exposure/true-multi-event** clips would strengthen segmentation
evidence.

## 20. Are we ready to freeze the Asset Understanding design? **NOT YET.**

Transport and model architecture are **well-determined** (frame-timeline Nova Pro primary +
Pegasus-for-long native option; async worker + presigned temp-S3 + per-object delete; App
Runner as control plane only; Photos-save for user ownership). What is **not** yet settled, and
blocks a freeze:
1. **No AU ground-truth** → quality claims are validity + qualitative, not scored (§19).
2. **The 154s native failure** needs a decision: cap native at a duration and fall back to
   frame-timeline, or chunk long clips — pick after the annotations exist.
3. **The AU output schema** is experimental; it should be exercised against ground truth before
   becoming a (new, non-canonical) MomentUnderstanding contract.

Recommend: a short **annotation pass (§19)** + a **finalist re-score**, THEN freeze. Everything
needed to do that is in place (subset, schema, runner, both transports proven).

---

---

# COST ACCOUNTING (added 2026-10-05)

**Pricing basis (ESTIMATE):** AWS Bedrock on-demand, us-east-1, public per-1k-token
pricing recorded **2026-10-05**: Nova Pro **$0.0008 in / $0.0032 out**; Nova Lite
**$0.00006 / $0.00024**; Sonnet 4.6 **$0.003 / $0.015**; Opus 4.5 **$0.015 / $0.075**.
TwelveLabs Pegasus per-token video pricing was not reliably determinable from the account
→ marked ESTIMATE below, not fabricated. All $ are approximate. Raw per-call usage:
`evals/results/au_density_cost.json` + `asset_understanding_exp.json` (gitignored).

Measured token facts (exact, from the runs): Nova Pro frame-timeline ≈ **~733 input tok /
frame** (8.9k @12fr → 71.5k @96fr; near-linear); Opus ≈ **~784 tok/frame** (18.8k @24fr,
37.5k @48fr — Opus tokenizes images denser); output ≈ 400 tok (Nova) / 600–1200 (Opus/Sonnet);
native video ≈ **2.3k tok (4s) → 27.5k (95s) → ~44k (154s)**.

## Frame-density scaling — Nova Pro (8-clip subset, exact usage)

| frames | event med | useful med | latency p50 | input tok | $/Moment | rel. vs 24fr |
|---:|---:|---:|---:|---:|---:|---:|
| 12 | 3.0 | 2.5 | 4.8s | 8,899 | **$0.0083** | 0.54× |
| **24** | **4.0** | **3.0** | 9.1s | 17,695 | **$0.0154** | **1.0× (baseline)** |
| 48 | 4.5 | 3.0 | 12.8s | 35,287 | $0.0296 | 1.9× |
| 96 | 3.5 ⬇ | 2.0 ⬇ | 20.8s | 71,495 | $0.0584 | 3.8× |

**Saturation point = ~24 frames.** 12→24 is a clear quality gain (events 3→4, useful 2.5→3)
for ~2× cost — worthwhile. 24→48 adds only marginal richness (events 4→4.5) for ~2× cost —
diminishing. **48→96 DEGRADES quality** (events 4.5→3.5, useful 3→2) at ~2× cost — strictly
not worthwhile (too many stills dilute the read). So the densest representation is *worse*,
not just not-worth-it. **Pick 24; 48 only if an annotation pass shows a real segmentation gain.**

## Cost normalization (median $/Moment → Story sizes)

| model / representation | $/Moment | 20 Moments | 50 Moments | 100 Moments |
|---|---:|---:|---:|---:|
| Nova Pro + 12 frames | $0.0083 | $0.17 | $0.41 | $0.83 |
| **Nova Pro + 24 frames** | **$0.0154** | **$0.31** | **$0.77** | **$1.54** |
| Nova Pro + 48 frames | $0.0296 | $0.59 | $1.48 | $2.96 |
| Nova Pro + 96 frames | $0.0584 | $1.17 | $2.92 | $5.84 |
| Opus 4.5 + 24 frames | $0.3374 | $6.75 | $16.87 | $33.74 |
| Opus 4.5 + 48 frames | $0.6208 | $12.42 | $31.04 | $62.08 |

$/minute-of-video is not a stable unit for frame-timeline (cost tracks frame COUNT, not
duration — a duration-scaled budget caps frames), so $/Moment is the meaningful unit. For
native video it would track duration; see Pegasus below.

## Opus cost comparison (IDENTICAL 24-frame evidence)

| metric | Nova Pro 24fr | Opus 4.5 24fr | delta |
|---|---:|---:|---|
| event recall (median) | 4.0 | **6.0** | +2 events (+50%) |
| useful segments | 3.0 | 3.0 | — |
| latency p50 | 9.1s | 19.8s | 2.2× slower |
| $/Moment | $0.0154 | $0.3374 | **~22×** |
| 100-Moment Story | $1.54 | **$33.74** | +$32.20 |

**Quality gain per additional cost:** Opus buys ~+50% event granularity (and qualitatively
sharper temporal language — it was one of the two arms that nailed reverse-reveal direction)
for **~22× the per-Moment cost**. Answering the brief's own example question: a +50% event
recall for 22× cost does **NOT** justify Opus on *every* Moment at MVP economics ($33.74 vs
$1.54 per 100-Moment Story). Opus is a **quality ceiling / selective-use** candidate (e.g. only
on long multi-event Moments where recall matters), not the default. Quality remains primary,
but the tradeoff is explicit: Nova Pro 24fr is the cost/performance frontier; Opus is the
ceiling.

## Native Pegasus cost (ESTIMATE)

Pegasus per-token video pricing wasn't reliably determinable from the account, so cost is an
estimate. Operational facts measured: native path = whole-video → temp S3 → model → delete.
- video duration handled: up to **154s** (the clip Nova native failed); rejects <~2s.
- latency: 5–19s model-side (short→154s).
- **S3 ancillary cost is trivial** (a 214MB object for <1 day ≈ well under $0.01 storage +
  pennies of PUT/GET). **But the real cost is NOT dollars** — it is **mobile upload latency +
  bandwidth** (a 214MB clip over cellular can take tens of seconds to minutes) and
  **architecture complexity** (presigned upload, worker, cleanup). Do not collapse that into a
  dollar figure.

**Frame-timeline vs native — infrastructure implication:**
- **Frame-timeline:** local frame extraction → **small request** (24 JPEGs ≈ a few MB) → model.
  No whole-video upload. Fits even a synchronous path.
- **Native video:** whole-video upload → temp S3 → model → delete. S3 $ small; upload
  latency/bandwidth and operational complexity are significant.
This is the decisive non-dollar factor favoring frame-timeline as the default.

## Hierarchical analysis cost

Not run as a separate multi-call arm (single-pass whole-timeline was sufficient on this
corpus). Projected if adopted: PASS1 (coarse, ~12fr ≈ $0.008) + PASS2 (deeper on ~1–2 regions,
~24fr ≈ $0.015 each) ≈ **$0.023–0.038/Moment on Nova Pro**, i.e. a ~1.5–2.5× multiplier and 2–3
model calls per Moment. **Decision:** not justified yet — single-pass 24fr already clears the
qualitative bar; revisit only if the annotation pass shows single-pass misses events on long
multi-event clips.

## Async infrastructure cost (MVP scale)

Separate FIXED/IDLE from VARIABLE:
- **A. App Runner + small frame-timeline requests:** fixed = the App Runner instance already
  running for C1–C3 (no new idle cost); variable = the per-Moment model cost above. **Negligible
  added fixed cost.**
- **B. App Runner control plane + SQS/worker:** SQS at MVP volume is effectively free (first 1M
  requests/mo free); a worker (small Fargate/Lambda) adds minor fixed/idle cost. At tens of
  Moments/day this is **pennies/month fixed**.
- **C. temp S3 + worker + native inference:** S3 transient storage negligible; worker as in B;
  native inference cost ≈ frame-timeline or less in tokens, but upload bandwidth is the real cost.
**At MVP scale the infra fixed cost is negligible; the variable per-Moment model cost dominates.**
Don't over-model it.

## Local-device cost (operational, not dollars)

Frame extraction (the Swift AVFoundation sampler): ~0.7s per clip offline incl. decode on a Mac;
on-device at capture the decode is already paid by the capture pipeline, so marginal cost is a
few hundred ms + 24 small JPEG encodes. Resulting network bytes: **~1–3 MB** (24 frames) vs
**19–214 MB** for whole-video upload — frame-timeline is ~10–100× less uplink. No fake $ assigned;
battery/CPU impact is minor and bounded (not continuous).

## FINAL quality / latency / cost frontier

| approach | event recall | useful seg | temporal | valid | p50/p95 | $/Moment | $/50 | infra complexity |
|---|---:|---:|---|---:|---:|---:|---:|---|
| **Nova Pro 24fr (frame-timeline)** | 4.0 | 3.0 | good | 100% | 9.1s/~14s | **$0.0154** | **$0.77** | **low** (small request) |
| Nova Pro 48fr | 4.5 | 3.0 | good | 100% | 12.8s | $0.0296 | $1.48 | low |
| **Opus 4.5 24fr** | **6.0** | 3.0 | **sharpest** | 100% | 19.8s/~24s | $0.3374 | $16.87 | low |
| Pegasus native | 3 | 2 | good (missed 1 arrival) | ~96% | 8.7s/~15s | ~est | ~est | **high** (upload+worker+S3) |
| hierarchical (projected) | ~5 | ~3.5 | good | — | ~20s | ~$0.03 | ~$1.5 | medium (2 calls) |

- **QUALITY CEILING:** **Opus 4.5 @ 24–48 frames** — best event recall + sharpest temporal
  language, regardless of cost.
- **COST/PERFORMANCE FRONTIER:** **Nova Pro @ 24 frames** — 100% valid, ~$0.015/Moment, good
  temporal/segmentation, low infra, no clip-length ceiling.
- **SIMPLEST ACCEPTABLE MVP:** **Nova Pro @ 24 frames, frame-timeline, via the existing async
  worker** — clears the qualitative bar with the least architecture (no native-video upload
  path). Pegasus-native is reserved for long multi-event Moments IF the annotation pass shows
  frame-timeline misses events there.

These are deliberately **three different answers**; the production pick (for review) is the
frontier (Nova Pro 24fr) with Opus as an optional per-Moment escalation on long multi-event
clips — not the cheapest (12fr degrades recall) and not the ceiling (Opus 22× cost).

## THIS experiment's spend (actual, estimate)

| item | calls | est cost |
|---|---:|---:|
| density/cost run — Nova Pro | 32 | $0.75 |
| density/cost run — Opus 4.5 | 16 | $7.82 |
| prior AU run (Nova/Sonnet, 26×~4 arms) | ~105 | $1.10 |
| prior AU run — Pegasus | 25 | <$0.50 (est) |
| transport/discovery probes (incl 1×44k native) | ~12 | $0.30 |
| S3 (transient, 1-day lifecycle, emptied) | — | <$0.05 |
| **TOTAL (estimate)** | **~190 calls** | **~$10.5** |

**Under the $20 threshold.** Opus density was the dominant cost; I capped Opus at 24+48 frames
(not all four densities) specifically to stay well under budget while still measuring the
quality/cost delta — the Opus question only needs a fixed sensible density, not the full sweep.

---

## Experiment hygiene
- Temp S3 bucket `story-assetunderstanding-exp-…` : private (public-access-block), opaque keys,
  **1-day lifecycle**, each object **deleted immediately after its analysis**; bucket emptied at
  end. Derived frames lived under the gitignored `private_local/frames/au` and were deleted. No
  permanent cloud media. No canonical contract touched. No async infra built. No Music/Edit
  Planner. STOP.


---

# FINAL GROUND-TRUTH EVALUATION — AU model selection (2026-10-05)

The intelligence/transport and density/cost experiments above established the frame-timeline
candidate (24 timestamped frames, Nova Pro) qualitatively. This final gate scores FOUR finalists
against **owner-approved human ground truth** — the one thing missing before a model can be frozen.

**Verdict: the earlier qualitative read was partly wrong. Nova Pro is the WEAKEST on grounded
understanding; a reasoning model (Opus 4.6 or Sonnet 4.6) is materially better from the SAME 24
frames — a model-limited gap, not evidence-limited. Native video (Pegasus) recovers nothing the
frame timeline loses. Recommendation below is a genuine product tradeoff, NOT auto-cheapest.**

## 1. Annotation subset (18 clips)
Drawn from the AU subset; full coverage: short (6) / medium (5) / long (6, incl. 95s + 154s) +
temporal (departure/arrival/reveal/progression/contradiction), semantics (difficulty/companionship/
end-of-day/wrong-people/beautiful-wrong-purpose/useful-elsewhere), multi-event (S07_A, S08_D), and
controls (static backpack ×2, camera-points-away, shared-source A01/A06). Easy + hard mixed.

## 2–3. Ground truth + owner review — APPROVED
AI-proposed annotations were visually grounded via timestamped contact sheets (not filenames), then
**owner-reviewed and approved 2026-10-05** with 6 rulings applied:
1. S02_A departure begins at **gear-up (0s)**, not the walk-out.
2. S02_D = **departure / threshold-crossing**.
3. S07_A = **companionship partial + useful_elsewhere**.
4. S08_D = **eating a pouch meal, NOT cooking** (filename 'cooking' is a hallucination trap, kept as-is).
5. S08_F = **breakfast, not dinner**; strong_elsewhere (window vista is the payoff).
6. S04_A = tiny person **confirmed present** (recall probe).
Fixture filenames are kept as-is on purpose — they encode the *requested capture intent*, not the
footage content; that mismatch IS the semantic test. Frozen as `au.ground_truth/1-approved`
(`evals/asset_understanding/ground_truth.json`).

## 4. Finalists (controlled)
All three frame-timeline arms got **IDENTICAL** evidence: 24 ordered timestamped frames, same
resolution/compression/prompt/schema — a pure MODEL comparison (no density sweep).
- **A ft_nova_pro** `amazon.nova-pro-v1:0`
- **B ft_sonnet** `us.anthropic.claude-sonnet-4-6`
- **C ft_opus** `us.anthropic.claude-opus-4-6-v1` — strongest **invocable** Opus. (`opus-5-5` is listed
  in inference profiles but returns **AccessDenied** on invoke; §4C "discover, don't assume" paid off.)
- **D nv_pegasus** `us.twelvelabs.pegasus-1-2-v1:0` — native whole video (S3 source).

## 5–6. Ground-truth metrics (LLM judge, Nova Pro, tolerant ±3s temporal matching; NO output repair)

| arm | event P | event R | **F1** | halluc | over-seg | **temporal (order)** | seg cov | **valid rate** | p50/p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Nova Pro 24fr | 0.54 | 0.59 | **0.56** | 35 | 47 | **9/18** | 0.70 | **18/18** | 9.8/13.7s |
| Sonnet 4.6 24fr | 0.78 | 0.85 | **0.80** | 10 | 52 | **16/17** | 0.81 | 17/18 | 26/33s |
| Opus 4.6 24fr | 0.73 | 0.78 | **0.75** | 17 | 55 | **17/18** | 0.78 | **18/18** | 30/38s |
| Pegasus native | 0.66 | 0.72 | 0.68 | 30 | **22** | 10/17 | **0.83** | 17/18 | 9.3/16.6s |

- **SEMANTIC QUALITY (valid outputs):** Sonnet best F1 (0.80) + fewest hallucinations (10); Opus best
  temporal (17/18) + best Story-semantics (story_utility 17/18, shot-contribution 8/18). Nova Pro worst
  on every understanding axis (F1 0.56, **35 hallucinations**, temporal **9/18**) — it emitted 24 events
  on a 6s clip and 12 on a 10s clip (gross over-segmentation).
- **RELIABILITY (end-to-end, no repair):** Nova 18/18, **Opus 18/18**, Sonnet **17/18** (truncated the
  154s clip at the output-token cap → invalid JSON — its known structured-output weakness), Pegasus
  17/18 (hard `ValidationException` on the 2.0s clip — too short for native video).
- **Temporal note:** the judge's raw boolean conflated "order correct" with "matched requested shot";
  corrected from the judge's own rationale text, true temporal-ORDER accuracy is Opus 17/18, Sonnet
  16/17, Nova 9/18, Pegasus 10/17. All four correctly read the reverse-reveal (landscape→person) and
  the arrival-not-departure case *as events* — but Nova/Pegasus failed the subtler contradiction/scale
  ordering that Opus/Sonnet nailed.

## 7. Model-limited vs evidence-limited (REQUIRED)
Because A/B/C share the exact 24 frames: where Nova missed a GT event that Sonnet and/or Opus caught
from the **same frames**, the limit is **reasoning, not evidence** — this dominates (≈17 such cases;
count is directional, cross-arm label matching is soft). Where ALL three frame arms missed something
Pegasus-native caught: **≈0**. **Conclusion: the 24-frame timeline is NOT evidence-starved for this
corpus; the gap between Nova and the reasoning models is model-limited.** Native continuous video did
not recover temporal/event information the timeline lost (Pegasus temporal 10/17 < Opus/Sonnet). This
is the decisive architectural result: **richer evidence (native video) is not the lever; a stronger
reasoner on the same frames is.**

## 8. Cost (real measured tokens; us-east-1 on-demand, recorded 2026-10-05 — ESTIMATE)

| arm | $/Moment | $/20 | $/50 | $/100 | notes |
|---|---:|---:|---:|---:|---|
| Nova Pro 24fr | $0.0164 | $0.33 | $0.82 | $1.64 | med 18.6k in / 0.5k out |
| Sonnet 4.6 24fr | $0.0799 | $1.60 | $4.00 | $7.99 | med 19.6k in / 1.4k out |
| **Opus 4.6 24fr** | **$0.3956** | **$7.91** | **$19.78** | **$39.56** | med 19.6k in / 1.35k out |
| Pegasus native | ~$0.03 (est) | ~$0.6 | ~$1.5 | ~$3 | **video-token $ not exposed** via InvokeModel → estimate; + whole-video upload/S3/worker |

**Opus is ~24× Nova and ~5× Sonnet per Moment.** Pegasus dollar cost is small but its real cost is
**operational**: whole-video mobile upload (19–214 MB vs ~1–3 MB of frames), temp S3, async worker,
cleanup/lifecycle, a second model path + second eval surface — none of which the frame arms need.

## 9. Frontier — three different answers (as the brief predicted)
- **QUALITY CEILING:** **Sonnet 4.6** has the best event F1/hallucination, **Opus 4.6** the best
  temporal + Story-semantics + reliability. The reasoning ceiling is clearly ABOVE Nova, from identical
  frames. If one must name a single ceiling: **Opus 4.6** (best temporal + Story-contribution + 100%
  valid), with Sonnet a close, cheaper, slightly-less-reliable alternative.
- **COST/PERFORMANCE FRONTIER:** **Sonnet 4.6 @ 24fr** — ~80% of Opus's understanding (actually higher
  event F1) at **1/5 the cost** ($4 vs $19.78 / 50 Moments) and faster, but **17/18 reliability** is the
  catch. OR **Opus @ 24fr** if 100% structured reliability is required and $20/50-Moments is acceptable
  for dogfood.
- **SIMPLEST ACCEPTABLE MVP:** **Nova Pro @ 24fr** is cheapest/fastest/most-reliable but **does NOT
  clear the quality bar** — F1 0.56, 35 hallucinations, temporal 9/18. For an understanding layer that
  feeds the Director and a future Edit Planner, Nova's hallucination/temporal weakness is a real risk.

## 10. Final model recommendation — ONE path
**Recommend Opus 4.6 @ 24-frame timeline as the single MVP/dogfood Asset Understanding model**, OR
**Sonnet 4.6 @ 24fr** if cost/latency matters more than perfect structured reliability. Rationale:
- Nova is tempting (cheap, 100% valid) but its grounded quality is the worst of the four — and AU
  output is *consumed* by Director reasoning and the future Edit Planner, where 35 hallucinated events
  and 9/18 temporal accuracy propagate downstream. Per §10C, do not sacrifice core intelligence to
  minimize early dogfood cost: at MVP volumes (tens of Moments/Story) Opus is **$8–20 per Story**, Sonnet
  **$1.6–4** — affordable for the quality gained.
- **No routing.** Duration did not predict semantic difficulty (the 6s S04 and 10s S02_D broke Nova
  harder than the 154s clip broke Opus). A second path (Nova-normal / Opus-long) would add logic,
  a failure surface, a model dependency and an eval problem it did not earn. **One model, all durations.**
- **Pegasus / native video is NOT justified.** Marginal-to-negative quality vs the frame reasoners,
  worst-of-both on temporal, and it alone demands upload/S3/worker/lifecycle infrastructure. §10D's bar
  ("native materially improves because the timeline loses information") is **not met** — §7 shows the
  timeline is not the bottleneck.

**Open product question for you:** Opus (100% reliable, +temporal, ~$8–20/Story) vs Sonnet (cheaper,
higher event F1, but 17/18 reliability — the one failure was recoverable with a higher output-token cap
or a retry). My lean: **Sonnet 4.6 with a retry-on-invalid guard** gets the best understanding at 1/5
Opus cost; fall back to **Opus** if you want zero structured-output failures without a retry layer.

## 11. Infrastructure consequence
A frame-timeline model wins → **simplest architecture**: iPhone extracts 24 timestamped frames
locally → small (~1–3 MB) AU request → selected model → MomentUnderstanding. **No whole-video S3
upload, no Fargate/Lambda video worker, no temp-media lifecycle.** AU stays *logically* async/resumable
as a **persistent on-device job queue** that posts the small frame request to the existing App Runner
inference endpoint when network permits — the individual model call completes synchronously (p50 9–30s,
well under App Runner's 120s), while the product workflow remains asynchronous. MVP needs **no** server
SQS / worker / temp S3. (If native video were ever adopted, only THEN build device→presigned-S3→async
job→native model→delete + lifecycle backstop — not now.)

## 12. MomentUnderstanding contract recommendation (minimum, consumer-justified)
Keep only fields with a real consumer (Story Coverage / Director / future Edit Planner):
- **summary** — Coverage/Director quick read ✅
- **subjects** — Coverage ✅
- **events[] (t_start, t_end, description)** — Edit Planner candidate material ✅
- **temporal_order_note** — Director (departure/arrival/reveal direction) ✅
- **useful_segments[] (start, end, why)** — Edit Planner inputs ✅ (the single most load-bearing field)
- **story_utility (none/useful_elsewhere/strong_elsewhere)** — Coverage/Director ✅
- **requested_shot_contribution / requested_beat_contribution** — Director ✅ (keep SEPARATE from
  observed events — observed reality is request-independent; contribution is the Story-context judgment)
- **DROP for MVP:** `environment` (subsumed by summary; no distinct consumer), `dead_or_setup_segments`
  (weakly detected across all models — segcov driven by useful_segments; revisit when the Edit Planner
  actually needs trim hints). This is a RECOMMENDATION; canonical contracts are NOT modified here.

## 13. Photos persistence — see companion doc
Implemented as an independent product-safety task: `milestone-d-photos-persistence.md` (add-only
`PhotosSaver`, fire-and-forget from `persistMoment`, migration-free, `swiftc -parse` clean). Open item:
add `PhotosSaver.swift` to the Xcode project. Not entangled with AU model selection.

## 14. This evaluation's spend (ESTIMATE, us-east-1 on-demand 2026-10-05)
- Nova finalist: 18 calls ~$0.30 · Sonnet: 18 ~$1.44 · **Opus: 18 ~$7.12 (dominant)** · Pegasus: 18
  ~$0.54 (video-token $ unknown → estimate) · Nova judge: 71 ~$0.25 · probes + S3 ~$0.10.
- **Total ≈ $9.74** — under the $20 gate (projected $8.25 beforehand; Opus output tokens ran higher).
  Pricing marked ESTIMATE; Pegasus per-video-token pricing not reliably determinable → flagged, not
  fabricated.

## Are we ready to freeze AU? (§20 from the prior report, now answered)
**YES — the model-selection gate is cleared.** We have human-approved ground truth and a controlled,
scored comparison. The remaining decision is the **one product call in §10** (Opus vs Sonnet). Once you
pick, the AU design can freeze on: **one reasoning model @ 24-frame local timeline, no native video, no
routing, on-device async queue + existing App Runner endpoint**, with the §12 minimum
MomentUnderstanding contract. The only data gap that could still move the needle is more ground-truth
clips (18 → ~30) if you want tighter confidence intervals before committing — optional, not blocking.

Experiment hygiene: temp S3 emptied (per-clip immediate delete + 1-day lifecycle backstop), derived
finalist frames deleted, no permanent cloud media, no canonical contract modified, no async infra
built, no Music/Edit Planner. STOP.
