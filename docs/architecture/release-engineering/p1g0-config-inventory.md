# P1-G0 — Configuration Inventory & Ownership (Stage A)

> **Update:** the cleanup this inventory fed is implemented on `fix/prebeta-release-config-gates`; result, exact deletions, counts and rollback are in [`p1g0-cleanup-result.md`](p1g0-cleanup-result.md). Rows below describe the pre-cleanup baseline (Audit 3).

**Status: STAGE A (inventory + findings + recommendations) — OFFLINE, no code behavior changed, not merged, not deployed.**
Branch `fix/prebeta-release-config-gates` off master `7797b13`. Beta runtime untouched. Signing/scheme preserved.

**Latest audit: "Audit 3" at the end of this file (master 2d2d379, 2026-11-12). It supersedes Audit 1 and Audit 2 where they disagree.**

This is the discovery deliverable. Stages B–F (consolidation, validators, runtime diagnostics, deploy/promotion gates, tests) are proposed at the end and NOT yet implemented — several need an owner decision first (§ Open decisions).

## 0. Ground truth verified this run (not from a status report)
- Master HEAD: `7797b13`. Worktrees: main + 3 unrelated (`observability`, `p0-evidence`, `p1a-semantics`) — untouched.
- **Dev API (App Runner `story-development-api`) effective:** `STORY_EDIT_PLAN_VERSION=5.3`, `STORY_EVIDENCE_PERSIST_ENABLED=1`, `STORY_GUIDE_V2=1`, `STORY_SCENE_IMAGES=1`, `STORY_MODEL_PROVIDER=direct`, `STORY_REQUIRE_AUTH=0`, `STORY_ENVIRONMENT=development`. **Dev worker** `STORY_EDIT_PLAN_VERSION=5.3`. (Both post-PR #69.)
- **Beta effective: UNOBSERVABLE this run.** No `story-beta-api` / `story-beta-edit-plan-worker` in the default account (989088054552); beta lives under the `yotale-beta` profile whose **SSO token is expired**. Beta "effective" columns below are therefore marked `unknown (SSO expired)` — NOT inferred. Owner must `aws sso login --profile yotale-beta` to populate them.
- A secrets gate already exists: `scripts/verify-required-secrets.sh "$ENVIRONMENT"` runs in `deploy-beta.yml`. Extend, do not duplicate.

## 1. Key findings (the incidents, mapped to concrete causes)

### F1 — Incident A (5.2 revert): CDK was the authoritative source all along
`STORY_EDIT_PLAN_VERSION` is now env-gated in CDK (`development`→`5.3`, else `5.2`; `-c editPlanVersion=` override) at lines 313 (worker) and 530 (service). Root cause of the historical revert: a **manual env flip wiped by App Runner/Lambda full-replace on `cdk deploy`**. Fixed durably (PR #69). **Gate needed (Stage E):** deploy must FAIL if API and worker versions disagree, or if the deployed worker image lacks the resolved prompt dir (`prompts/edit_plan/<ver>/`).

### F2 — Incident B (reuse activation): `STORY_REUSABLE_EVIDENCE` is a **dead backend env var**
CDK sets `STORY_REUSABLE_EVIDENCE=1` on App Runner (line 538) but **no Python code reads it** (grep: 0 backend hits). The real device control is the iOS `StoryReusableEvidence` flag (`ProcessInfo`/UserDefaults, default OFF). The two real controls are: backend `STORY_EVIDENCE_PERSIST_ENABLED` (persist) + iOS `STORY_REUSABLE_EVIDENCE` (reuse). **Recommendation:** remove the dead App Runner `STORY_REUSABLE_EVIDENCE` entry (consolidation) and model "reusable_evidence" as ONE capability in the manifest that derives BOTH the backend persist flag and the client-feature requirement, so one accepted capability can't be half-enabled.

### F3 — Incident C (diagnostics): two independent controls, confusing sink
- `STORY_REUSABLE_EVIDENCE` (iOS) = behavior ON/OFF. `STORY_DIAG_BEACONS` (iOS) = diagnostic emission ON/OFF. Independent — a missing beacon ≠ feature OFF.
- Beacon sink: `MediaEngineV1.beacon` (MediaEngineV1.swift:250) fires `GET /health?music=<note>` — lands in the backend access log, NOT the Xcode console, and only when `STORY_DIAG_BEACONS=1`. This is the confusing/fragile design §12 flags. **Recommendation (bounded):** keep `/health?music=` for cross-component correlation but add device-local `os_log`/structured logging as the primary device sink, and a **non-AI feature-state introspection** (see F6) so activation is inspectable WITHOUT running a Story.

### F4 — Incident D (Xcode scheme): duplicates + parallel disabled beta creds
Scheme carries duplicate active `STORY_EDITORIAL_TYPE_V2=1` and `STORY_REUSABLE_EVIDENCE=1`, plus a disabled beta API URL + beta Cognito row alongside the enabled dev ones. **Recommendation:** move environment selection to xcconfig/build-configuration (Dev build config → dev infra; Beta/Release build config → beta infra), drop the disabled-row/checkbox dance, and add a validator that FAILS on any duplicate active scheme key (even identical values). NOTE: the scheme is the owner's personal file (uncommitted) — I will NOT edit it; the validator + an xcconfig scaffold is the deliverable, applied by the owner.

### F5 — No deploy-time config gate today
`deploy-dev.yml` / `deploy-beta.yml` run the secrets check but NO completeness/consistency/version-parity gate. This is the core Stage E work.

### F6 — No non-AI effective-config introspection
Today the only way to learn the effective edit-plan version / reuse state is to run AU + EditPlan + render (§14's complaint). There is `/health` but it doesn't report resolved config. **Recommendation (bounded, needs owner OK per §11):** an authenticated `GET /v1/deploy/config` (or extend `/health` with an authed detail mode) returning resolved, privacy-safe config (versions, capability states, artifact SHA, source-of-value) — the post-deploy runtime gate + §14 cheap check consume it. This is a new API contract → presented as a proposal, not implemented yet.

## 2. Inventory (release-managed parameters)

Legend — Decision: KEEP / CONSOLIDATE / REMOVE. Consumer: iOS / API / WK (worker) / CDK / CI.

### Infrastructure / auth (environment-specific — KEEP, isolate per env)
| Name | Consumer | Source | Dev eff. | Beta eff. | Secret | Decision |
|---|---|---|---|---|---|---|
| STORY_API_BASE_URL | iOS | scheme/xcconfig | ydmju5wdps… | unknown (SSO) | no | KEEP → xcconfig |
| STORY_COGNITO_USER_POOL_ID | iOS,API | scheme/CDK | us-east-1_AzfHOEdA5 | unknown | no | KEEP → xcconfig |
| STORY_COGNITO_APP_CLIENT_ID | iOS,API | scheme/CDK | 5rnvp7oq6d7… | unknown | no | KEEP → xcconfig |
| STORY_COGNITO_DOMAIN_PREFIX | iOS | scheme | story-development-auth | unknown | no | KEEP → xcconfig |
| STORY_COGNITO_REGION | iOS | scheme | us-east-1 | unknown | no | KEEP |
| STORY_COGNITO_REDIRECT_URI | iOS | scheme | story://auth | story://auth | no | KEEP |
| STORY_{MEDIA,STORIES,USERS,UNDERSTANDING,JOBS,RATE_LIMIT,USER_USAGE,IDENTITY_CLAIMS}_TABLE | API,WK | CDK | per-env | unknown | no | KEEP (CDK-owned) |
| STORY_{MEDIA,STAGING}_BUCKET, STORY_JOBS_QUEUE_URL | API,WK | CDK | per-env | unknown | no | KEEP (CDK-owned) |

### Product capabilities (candidates to CONSOLIDATE into the manifest)
| Name | Consumer | Default absent | Dev eff. | Decision |
|---|---|---|---|---|
| STORY_EDIT_PLAN_VERSION | API,WK | 5.2 | 5.3 | KEEP as rollback control; manifest sets intent 5.3; gate enforces API==WK |
| STORY_EDITORIAL_TYPE_V2 (iOS) | iOS | ON (true) | ON | CONSOLIDATE (accepted → default ON already; drop from scheme) |
| STORY_REUSABLE_EVIDENCE (iOS) | iOS | OFF | ON via scheme | CONSOLIDATE → capability `reusable_evidence`; flip accepted default ON for dev/beta after owner confirms (P1-F accepted) |
| STORY_REUSABLE_EVIDENCE (CDK/App Runner) | — | — | set but unread | **REMOVE (dead backend env, F2)** |
| STORY_EVIDENCE_PERSIST_ENABLED | API | OFF | 1 | KEEP (server persist gate); manifest ties to `reusable_evidence` capability |
| STORY_GUIDE_V2 | API | OFF(gate) | 1 | CONSOLIDATE (accepted) — confirm status |
| STORY_SCENE_IMAGES | API | OFF(gate) | 1 | CONSOLIDATE (accepted) — confirm status |
| STORY_MULTIMODAL_PLANNING (iOS) | iOS | ? | ? | CLASSIFY (owner: accepted vs rollback) |
| STORY_CRITIQUE_REVISION / STORY_CRITIQUE_EXPLORE / STORY_CREATIVE_REFINEMENT (iOS) | iOS | ? | ? | CLASSIFY (likely rollback/pending) |

### AI provider / model routing (KEEP — do NOT change routing here, §21)
`STORY_MODEL_PROVIDER` (dev=direct), `STORY_AU_MODEL`, `STORY_EDIT_PLANNER_MODEL`, `STORY_DIRECTOR_MODEL`, `STORY_COVERAGE_MODEL`, `STORY_GUIDE_MODEL`, `STORY_SCENE_MODEL`, `STORY_MUSIC_PLAN_MODEL`, `STORY_DURATION_PLANNER_MODEL`, `STORY_GEMINI_MODEL`, `STORY_OPENAI_MODEL`, `STORY_BEDROCK_MODEL` (legacy), `STORY_LLM_FALLBACK_MODEL`, `STORY_MUSIC_PROVIDER`. Decision: KEEP, inventory-register; the gate checks "no unapproved provider routing" but P1-G0 does not alter values.

### Operational / tuning (KEEP, CDK-owned)
`STORY_REQUIRE_AUTH`, `STORY_QUOTA_MODE` + `STORY_QUOTA_*`, `STORY_THROTTLE_MODE`/`_WINDOW_SECONDS`, `STORY_WORKER_CONCURRENCY`/`_DEADLINE_S`, `STORY_EDIT_PLANNER_MAX_TOKENS*`/`_REPAIR_ATTEMPTS`, `STORY_EDITPLAN_*` (soft-range/retention/objective), `STORY_EPIDEMIC_MODE`, `STORY_JOBS_API_ENABLED`, `STORY_EVIDENCE_{BUCKET,TABLE}`, `STORY_AWS_REGION`, `STORY_ENVIRONMENT`.

### Diagnostics (KEEP, must be independent of behavior — F3)
`STORY_DIAG_BEACONS` (iOS), `STORY_LAUNCH_CONFIG` print, `*_MOCK` switches (`STORY_ASSET_UNDERSTANDING_MOCK`, `STORY_GUIDE_MOCK`, `STORY_COVERAGE_MOCK`, `STORY_DIRECTOR_MOCK`, `STORY_SCENE_UNDERSTANDING_MOCK`, `STORY_CREATIVE_INTENT_MOCK`), `STORY_WORKER_ALLOW_TEST_DELAY`, `STORY_DOCS_PUBLIC`. Build provenance: Info.plist `GitCommitSHA`.

### Secrets (stay in secret manager — never in manifest/logs/scheme)
Provider API keys + Cognito client secret via `scripts/verify-required-secrets.sh`; GitHub Actions `secrets.*`. Inventory-register as references only.

## 3. Before/after consolidation (proposed)
- **Dead/removable now:** CDK `STORY_REUSABLE_EVIDENCE` (dead backend env, F2); duplicate scheme rows (F4); `STORY_EDITORIAL_TYPE_V2` from scheme (already default-ON accepted).
- **Consolidate under one manifest capability:** `edit_plan 5.3`, `reusable_evidence`, `editorial_v2`, `rich_au`, `story_guide_v2`, `scene_images` → derive backend/client flags from capability state instead of N remembered flags.
- Net: ~6 independently-remembered release flags → 1 manifest + derived values; dead/duplicate entries eliminated.

## 4. Open decisions (STOP points per §21 — need owner before Stage B)
1. **Accepted-status confirmation** for `STORY_GUIDE_V2`, `STORY_SCENE_IMAGES`, `STORY_MULTIMODAL_PLANNING`, critique/refinement flags — I will not change activation semantics while status is ambiguous.
2. **New diagnostic contract** `GET /v1/deploy/config` (F6/§11/§14) — a bounded new authed API. Proposal only; implement on approval.
3. **Beta effective values** — need `aws sso login --profile yotale-beta` to populate the beta columns and build the dev→beta parity gate (§16) against real data.
4. **Manifest format** — proposed: a `release.yaml` consumed by CDK context + a Swift build-time check, reusing existing patterns (no new remote config service). Confirm before authoring.


---

# Audit 2 — 2026-11-10 (master e10ebaf, after PRs #71–#101)

Method: repo grep (Python, Swift, CDK, workflows, xcconfig/schemes) + live read-only App Runner/Lambda env for dev and beta.
Nothing was changed, committed, merged or deployed. "Live" = read from AWS today. "Code" = read from source, not runtime-verified.

## 1. Live effective env (dev vs beta)

| Surface | Dev | Beta |
|---|---|---|
| App Runner service vars | 33 | 33 |
| Worker Lambda vars | 16 (15 STORY_* + PYTHONPATH) | 16 |

Identical in dev and beta (product behaviour is already at parity): EDIT_PLAN_VERSION=5.3 (service AND worker), GUIDE_V2=1, SCENE_IMAGES=1,
EVIDENCE_PERSIST_ENABLED=1 (service), MODEL_PROVIDER=direct, OPENAI_MODEL=gpt-5.1, GEMINI_MODEL=gemini-3.8-flash, REFERENCE_MEDIA_MODE=image,
MUSIC_PROVIDER=mcp, EPIDEMIC_MODE=prototyping, JOBS_API_ENABLED=1, QUOTA_GLOBAL_MONTHLY_USD=60, QUOTA_MAX_ACTIVE_JOBS=2, QUOTA_USER_DAILY_GENS=500,
worker EDITPLAN_{OBJECTIVE_DIRECTIVES,BEST_VALID_RETENTION,APPROX_DURATION_SOFT}=1, WORKER_DEADLINE_S=840, LLM_FALLBACK_MODEL=us.anthropic.claude-sonnet-4-6.

Differences (all intended): ENVIRONMENT, Cognito pool/client, all table/bucket/queue names; REQUIRE_AUTH 0 vs 1; QUOTA_MODE observe vs enforce;
THROTTLE_MODE observe vs enforce; QUOTA_USER_MONTHLY_USD 8 vs 50. Dev is the only env that is auth-optional and non-enforcing.

Not verified: that the deployed image digests correspond to master e10ebaf (no digest→SHA mapping done this pass).

## 2. Classification of every parameter found

### A. Product-feature gates (target: delete, behaviour becomes code)
| Param | Where | Code default | Live | Status |
|---|---|---|---|---|
| STORY_EDIT_PLAN_VERSION | CDK→service+worker | "5" (code!) | 5.3 | Accepted. Code default is stale (5), CDK ternary sets 5.3 for dev/beta only. Keep ONE documented rollback; default 5.3 in code. |
| STORY_GUIDE_V2 | CDK ctx guideV2, backend gate, iOS | iOS ON, CDK "1" | 1 | Accepted → remove backend gate, iOS env/UserDefaults path |
| STORY_SCENE_IMAGES | same | iOS ON, CDK "1" | 1 | Accepted → remove |
| STORY_EDITORIAL_TYPE_V2 | iOS | ON | n/a | Accepted (P1-D) → remove |
| STORY_REUSABLE_EVIDENCE | iOS (+ dead CDK mention in comment) | **OFF** (`_enabledDefault=false`, "OFF until device-accepted") | n/a | P1-F is accepted but default is STILL OFF → Incident B still reproducible |
| STORY_EVIDENCE_PERSIST_ENABLED | CDK ctx evidencePersist, main.py:1315 | "0" | 1 (dev+beta) | Privacy kill-switch for durable personal frames. NOT a plain feature flag (see §5) |
| STORY_EDITPLAN_OBJECTIVE_DIRECTIVES / BEST_VALID_RETENTION / APPROX_DURATION_SOFT | worker only | OFF in code | 1 | Accepted invariants → hardwire, delete. |
| STORY_EDITPLAN_USEFUL_RANGE_SOFT | code only | OFF | **not set anywhere live** | Unclear acceptance; an earlier lesson says it was defined but not wired. Owner decision. |
| STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE | code only | OFF | not set | Deliberate fail-safe escape hatch. Keep OFF; decide delete vs retain. |
| STORY_MULTIMODAL_PLANNING (iOS) | iOS | ON | n/a | Accepted kill-switch → remove |
| STORY_CREATIVE_REFINEMENT (iOS) | iOS | ON | n/a | Default ON; acceptance not re-verified |
| STORY_CRITIQUE_REVISION (iOS) | iOS | ON | n/a | Default ON; acceptance not re-verified |
| STORY_CRITIQUE_EXPLORE (iOS) | iOS | OFF | n/a | Unaccepted experiment. Leave OFF; owner decision |
| STORY_REFERENCE_MEDIA_MODE | CDK ctx referenceMedia, backend video endpoint, iOS | image | image | Two-sided enum. Video is parked (owner 2026-11-06). Temporary pending feature. |
| STORY_JOBS_API_ENABLED | service | "1" in code | 1 | Remove if the sync edit-plan path is retired (needs a check that iOS never calls it) |

### B. Environment infrastructure (keep, auto-supplied by CDK)
STORY_ENVIRONMENT; tables: JOBS, MEDIA, STORIES, UNDERSTANDING, RATE_LIMIT, USER_USAGE, USERS, IDENTITY_CLAIMS; buckets: MEDIA, STAGING; STORY_JOBS_QUEUE_URL;
STORY_COGNITO_USER_POOL_ID / APP_CLIENT_ID. Code also reads STORY_EVIDENCE_BUCKET and STORY_EVIDENCE_TABLE, which are NOT in the live env →
verify the fallback names resolve in dev and beta (the P1-F cache works on dev, so a fallback exists; confirm it on beta).

### C. Operational / security (keep)
STORY_REQUIRE_AUTH, STORY_QUOTA_MODE, QUOTA_{USER_MONTHLY_USD,USER_DAILY_GENS,MAX_ACTIVE_JOBS,GLOBAL_MONTHLY_USD}, QUOTA_SYNC_PRUNE_SAMPLE (code-only, 0.1),
STORY_THROTTLE_MODE, THROTTLE_{READ,WRITES,AI_SYNC,AI_JOB_SUBMIT,MUSIC,PRESIGN}_PER_MIN + WINDOW_SECONDS (code defaults only), STORY_WORKER_DEADLINE_S,
STORY_WORKER_CONCURRENCY (CDK build-time), STORY_EPIDEMIC_MODE, STORY_MUSIC_PROVIDER, STORY_DOCS_PUBLIC (default 0).
Beta currently correct: REQUIRE_AUTH=1, QUOTA=enforce, THROTTLE=enforce. deploy-beta.yml sets those from the workflow; deploy-dev.yml sets none (CDK default observe).

### D. AI routing
| Param | Live | Reality |
|---|---|---|
| STORY_MODEL_PROVIDER | direct (set by CDK) | **Code default is "bedrock"** (deps.py:271, worker.py:239). Any path that does not go through CDK silently targets restricted Anthropic. |
| STORY_OPENAI_MODEL / STORY_GEMINI_MODEL | gpt-5.1 / gemini-3.8-flash | The two real model knobs. Keep. |
| STORY_LLM_FALLBACK_MODEL (Anthropic) | set on service AND worker, dev+beta | Read only inside the non-direct branch (deps.py:253/275, worker.py:244/261). Unreachable in direct mode. Only residual use: worker.py:81 chooses it as a *label* for diagnostics `model_id` when any_fallback is true → can mislabel the model that actually ran. Safe to delete. |
| STORY_AU_MODEL, COVERAGE_MODEL, DIRECTOR_MODEL, GUIDE_MODEL, SCENE_MODEL, EDIT_PLANNER_MODEL, MUSIC_PLAN_MODEL, DURATION_PLANNER_MODEL, BEDROCK_MODEL, BEDROCK_ROUTED_MODEL, AWS_REGION(STORY_) | not set anywhere | Per-stage Bedrock overrides. In direct mode routing ignores them (some survive as metadata labels). Defaults are Anthropic/Nova ids. Delete the overrides. |
| STORY_ROUTE_<CAPABILITY> (provider.py:70) | not set | Per-capability "primary:fallback" override; used only by tests. Keep the routing table in code, drop the env override. |
| STORY_EDIT_PLANNER_{REPAIR_ATTEMPTS,MAX_TOKENS,MAX_TOKENS_CEILING} | not set | Tuning knobs at defaults (2/8192/16384). Candidates to hardcode. |

### E. Mocks / test-only (must never exist in a deployed env)
STORY_ASSET_UNDERSTANDING_MOCK, COVERAGE_MOCK, CREATIVE_INTENT_MOCK, DIRECTOR_MOCK, GUIDE_MOCK, SCENE_UNDERSTANDING_MOCK, STORY_WORKER_ALLOW_TEST_DELAY.
None is set live. The pre-deploy gate should reject them. STORY_MUSIC_COMMERCIAL_EXPORT is mentioned in code comments only (not a read).

### F. iOS configuration
- Environment identity is now correct and baked: STORY_BUILD_ENV + 6 STORY_ENV_* in `Config/{Development,Beta}.xcconfig` → Info.plist → `StoryEnvironment`.
  Release builds ignore process env and UserDefaults and fail closed on a dev/beta mismatch. This is the §7 separation, already merged via the TestFlight work.
- DEBUG still uses the legacy chain (scheme env → UserDefaults → dev default): STORY_API_BASE_URL, STORY_COGNITO_{USER_POOL_ID,APP_CLIENT_ID,DOMAIN_PREFIX,REGION,REDIRECT_URI}.
- Owner's uncommitted `Story.xcscheme` currently has: 7 enabled auth/API rows + 4 DISABLED beta duplicates (API_BASE_URL, POOL_ID, CLIENT_ID, DOMAIN_PREFIX),
  GUIDE_V2=1, SCENE_IMAGES=1, REFERENCE_MEDIA_MODE=image, launch arg `-STORY_MODE product`. No duplicate ENABLED keys now (Incident D improved).
  EDITORIAL_TYPE_V2, REUSABLE_EVIDENCE and DIAG_BEACONS are no longer in the scheme.
- **Consequence (code-read, not runtime-verified):** with REUSABLE_EVIDENCE removed from the scheme and the compiled default OFF, reusable evidence is OFF on any run
  without a persisted UserDefaults override. Backend persistence is ON, so the device would persist-but-never-reuse.
- Diagnostics: STORY_DIAG_BEACONS (reads env only; empty on TestFlight → effectively off), STORY_LAUNCH_CONFIG / STORY_ACTIVE_BACKEND (print only), STORY_MODE launch arg.
- STORY_APPLE_SIGNIN_AVAILABLE: new, default "0", read via StoryLaunchConfig (DEBUG chain). Confirm how a release build sets it.

### G. CDK/CI knobs
CDK context keys that change product behaviour: editPlanVersion, editplanV2, editplanV2Flags, evidencePersist, guideV2, sceneImages, referenceMedia, modelProvider, openaiModel, geminiModel (10).
`editplanV2` and `editplanV2Flags` are two overlapping switches for the same three worker flags. deploy-beta.yml and deploy-dev.yml both pass `-c editplanV2=true`.
The App Runner service never receives the three EDITPLAN flags (worker only); if the sync planner path is still reachable it plans under different rules than the worker.

## 3. Changes since Audit 1 (PRs #71–#101)
New: baked iOS env (STORY_BUILD_ENV, STORY_ENV_*), STORY_APPLE_SIGNIN_AVAILABLE, STORY_IDENTITY_CLAIMS_TABLE, STORY_USERS_TABLE, STORY_REFERENCE_MEDIA_MODE (backend+iOS),
STORY_QUOTA_SYNC_PRUNE_SAMPLE, STORY_WORKER_CONCURRENCY, STORY_ROUTE_*, WAF/auth CDK contexts. Counts: service 32→33, worker 14→15 STORY_* vars.
Product features added without a new flag: customize v2, AU background continuity, camera stabilization, hidden-directive fix, retime fix.
Per-feature check: none of them added an env var, which is the intended outcome.

## 4. Proposed deletions (PROPOSED only, nothing implemented)
Deploy-time (CDK/workflows): STORY_LLM_FALLBACK_MODEL (2 sites), STORY_GUIDE_V2, STORY_SCENE_IMAGES, the 3 STORY_EDITPLAN_* worker flags,
contexts guideV2 / sceneImages / editplanV2 / editplanV2Flags, workflow `-c editplanV2=true`. Optional: STORY_JOBS_API_ENABLED.
Code: per-stage *_MODEL / BEDROCK_* / STORY_ROUTE_* env reads; flip STORY_MODEL_PROVIDER code default to direct; set edit-plan code default to 5.3.
iOS: env + UserDefaults override paths for GUIDE_V2, SCENE_IMAGES, EDITORIAL_TYPE_V2, MULTIMODAL_PLANNING, REUSABLE_EVIDENCE (after flipping default ON); scheme rows for GUIDE_V2 / SCENE_IMAGES.
Retained: Section B, Section C, EDIT_PLAN_VERSION (single rollback), OPENAI/GEMINI models, EVIDENCE_PERSIST_ENABLED (pending decision), REFERENCE_MEDIA_MODE, DIAG_BEACONS (debug).

Counts (service, same for dev/beta): 33 → 29 if GUIDE_V2, SCENE_IMAGES, LLM_FALLBACK_MODEL, JOBS_API_ENABLED are deleted (EVIDENCE_PERSIST kept).
Worker: 15 → 10 (3 EDITPLAN flags + LLM_FALLBACK_MODEL + OPENAI/GEMINI kept). iOS product-feature toggles: 8 → 1–2.
Code-only env reads removed: ~17 (8 per-stage models, 2 bedrock, ROUTE_*, 3 planner tuning, mocks stay for tests).

## 5. Decisions needed from the owner
1. EVIDENCE_PERSIST_ENABLED: keep as a server-side privacy kill-switch (recommended; beta now stores testers' personal frames and account deletion is still design-only), or remove.
2. Flip iOS REUSABLE_EVIDENCE default to ON now (P1-F is accepted) — this is the direct fix for Incident B.
3. Acceptance status of CRITIQUE_REVISION, CREATIVE_REFINEMENT, CRITIQUE_EXPLORE, USEFUL_RANGE_SOFT, EXCLUDE_DEFAULT_CREATIVE.
4. Is the sync edit-plan path retired? If yes, delete JOBS_API_ENABLED and stop the service/worker flag asymmetry.
5. Branch/worktree: main worktree is on master with your uncommitted iOS files (pbxproj, Story.xcscheme, StoryHomeView.swift). `fix/prebeta-release-config-gates` has zero commits.

---

# Audit 3 — 2026-11-12 (master 2d2d379, after PRs #102–#106)

Method: full re-grep of Python, Swift, CDK, workflows, xcconfig and scheme on current master, plus live read-only App Runner and Lambda env for dev (989088054552) and beta (224033508028).
Nothing was changed, committed, merged or deployed by this audit. "Live" = read from AWS on 2026-11-12. "Code" = read from source, not runtime-verified.
Where this section disagrees with Audit 1 or 2, this section wins. Superseded Audit 2 items are listed in §4.

## 1. Live deployment state

| Surface | Dev | Beta |
|---|---|---|
| API image tag (ECR, resolved from the running digest) | `git-29f7f2f1ca02` (#105), pushed 2026-11-11 16:08 PST | `git-2d2d379998be` (#106 = current master), pushed 2026-11-11 22:45 PST |
| App Runner status | RUNNING | RUNNING |
| Worker Lambda last modified | 2026-11-12 00:09 UTC | 2026-11-12 06:45 UTC |
| Service env vars | 33 | 33 |
| Worker env vars | 16 (15 STORY_* + PYTHONPATH) | 16 (15 STORY_* + PYTHONPATH) |

- Dev API is one commit behind master (#106 "Honor Full Story on new versions; recover lost job replies"). #106 touched no env, CDK or workflow file, so this is a code lag only.
- Worker code revision is baked into a `BUILD_SHA` file inside the zip (not an env var), so I did not read it. Worker build parity with the API image is NOT verified.

## 2. Live effective env, side by side (service)

| Variable | Dev | Beta | Same? |
|---|---|---|---|
| STORY_ENVIRONMENT | development | beta | identity |
| STORY_COGNITO_USER_POOL_ID / APP_CLIENT_ID | AzfHOEdA5 / 5rnvp7oq… | 3cPNfbrUl / 4f3dtn9d… | identity |
| Tables (JOBS, MEDIA, STORIES, UNDERSTANDING, RATE_LIMIT, USER_USAGE, USERS, IDENTITY_CLAIMS), buckets (MEDIA, STAGING), JOBS_QUEUE_URL | `story-development-*` | `story-beta-*` | identity |
| STORY_EDIT_PLAN_VERSION | 5.3 | 5.3 | yes |
| STORY_GUIDE_V2 | 1 | 1 | yes |
| STORY_SCENE_IMAGES | 1 | 1 | yes |
| STORY_EVIDENCE_PERSIST_ENABLED | 1 | 1 | yes |
| STORY_JOBS_API_ENABLED | 1 | 1 | yes |
| STORY_REFERENCE_MEDIA_MODE | image | image | yes |
| STORY_MODEL_PROVIDER | direct | direct | yes |
| STORY_OPENAI_MODEL / STORY_GEMINI_MODEL | gpt-5.1 / gemini-3.8-flash | same | yes |
| STORY_LLM_FALLBACK_MODEL | us.anthropic.claude-sonnet-4-6 | same | yes (dead, see §3.D) |
| STORY_MUSIC_PROVIDER / STORY_EPIDEMIC_MODE | mcp / prototyping | same | yes |
| STORY_QUOTA_GLOBAL_MONTHLY_USD / MAX_ACTIVE_JOBS / USER_DAILY_GENS | 60 / 2 / 500 | 60 / 2 / 500 | yes |
| STORY_REQUIRE_AUTH | **0** | **1** | policy |
| STORY_QUOTA_MODE | **observe** | **enforce** | policy |
| STORY_THROTTLE_MODE | **observe** | **enforce** | policy |
| STORY_QUOTA_USER_MONTHLY_USD | **8** | **50** | policy |

Worker (15 STORY_* each): identical on both sides for EDIT_PLAN_VERSION=5.3, EDITPLAN_{OBJECTIVE_DIRECTIVES, BEST_VALID_RETENTION, APPROX_DURATION_SOFT}=1, GEMINI/OPENAI model, MODEL_PROVIDER=direct, LLM_FALLBACK_MODEL (Anthropic id), WORKER_DEADLINE_S=840.
Only identity differs (ENVIRONMENT, JOBS_QUEUE_URL, JOBS_TABLE, STAGING_BUCKET, USER_USAGE_TABLE) and QUOTA_MODE (observe vs enforce).

Result: dev and beta match on every product-behaviour value. Service planner and worker planner agree on 5.3 in both environments. Beta enforces auth, quota and throttling; dev does not.

## 3. Full parameter inventory (current master)

Counts of distinct `STORY_*` names found in source: about 70 backend reads (non-test Python), 17 iOS keys, 45 referenced in CDK.

### A. Product-feature gates (target: delete)
| Param | Surface | Code default | Live | Status |
|---|---|---|---|---|
| STORY_EDIT_PLAN_VERSION | CDK → service + worker; CI | `"5"` in code (`packages/edit_planner/__init__.py:69`) | 5.3 | Accepted. Code default is still stale; only CDK makes it 5.3. Make 5.3 the code default, keep as the single documented rollback. |
| STORY_GUIDE_V2 | CDK ctx, backend gate, iOS | iOS ON, CDK "1" | 1 | Accepted → delete. iOS still has env + UserDefaults paths (`StoryGuideFeatures.swift:18-25`). |
| STORY_SCENE_IMAGES | same | iOS ON, CDK "1" | 1 | Accepted → delete. |
| STORY_EDITORIAL_TYPE_V2 | iOS | ON | n/a | Accepted (P1-D) → delete env/UserDefaults path. |
| STORY_MULTIMODAL_PLANNING | iOS | ON | n/a | Accepted kill-switch → delete. |
| STORY_CREATIVE_REFINEMENT | iOS | ON | n/a | Default ON; acceptance not confirmed by owner. |
| STORY_CRITIQUE_REVISION | iOS | ON | n/a | Default ON; acceptance not confirmed by owner. |
| STORY_CRITIQUE_EXPLORE | iOS | OFF | n/a | Unaccepted experiment. Leave OFF; owner decision. |
| STORY_EVIDENCE_PERSIST_ENABLED | CDK ctx `evidencePersist`, `main.py` | "0" | 1 (dev + beta) | Privacy kill-switch for durable personal frames. Keep pending owner decision (account deletion is still design-only). |
| STORY_EDITPLAN_OBJECTIVE_DIRECTIVES / BEST_VALID_RETENTION / APPROX_DURATION_SOFT | worker only | OFF in code | 1 | Accepted invariants → hardwire and delete. |
| STORY_EDITPLAN_USEFUL_RANGE_SOFT | none (already removed) | — | not set | **Already deleted from code.** Soft behavior is the permanent default (`packages/edit_planner/__init__.py:922`); only a test `delenv` and comments remain. Nothing to decide. |
| STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE | code + CDK | OFF | not set | Deliberate fail-safe. Owner decision. |
| STORY_REFERENCE_MEDIA_MODE | CDK ctx, backend, iOS | image | image | Video is parked. Temporary pending feature. |
| STORY_JOBS_API_ENABLED | service | "1" | 1 | Delete if the sync edit-plan path is retired (owner decision). |
| ~~STORY_REUSABLE_EVIDENCE~~ | iOS | — | — | **Already removed in #102.** See §4. |

### B. Environment infrastructure (keep, CDK-supplied)
STORY_ENVIRONMENT; tables JOBS, MEDIA, STORIES, UNDERSTANDING, RATE_LIMIT, USER_USAGE, USERS, IDENTITY_CLAIMS; buckets MEDIA, STAGING; JOBS_QUEUE_URL; COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID.
Code also reads STORY_EVIDENCE_BUCKET and STORY_EVIDENCE_TABLE, which are not set live. P1-F evidence storage reuses the media bucket and table, so these are fallback overrides only.

### C. Operational / security (keep)
STORY_REQUIRE_AUTH, STORY_QUOTA_MODE, QUOTA_{USER_MONTHLY_USD, USER_DAILY_GENS, MAX_ACTIVE_JOBS, GLOBAL_MONTHLY_USD}, QUOTA_SYNC_PRUNE_SAMPLE (code-only),
STORY_THROTTLE_MODE, THROTTLE_{READ, WRITES, AI_SYNC, AI_JOB_SUBMIT, MUSIC, PRESIGN}_PER_MIN + WINDOW_SECONDS (code defaults only),
STORY_WORKER_DEADLINE_S, STORY_WORKER_CONCURRENCY (CDK build-time), STORY_EPIDEMIC_MODE, STORY_MUSIC_PROVIDER, STORY_DOCS_PUBLIC (default 0).

### D. AI routing
- STORY_MODEL_PROVIDER: live `direct`, but the **code default is still `bedrock`** (`deps.py`, `worker.py`). A run that bypasses CDK would target restricted Anthropic models.
- STORY_OPENAI_MODEL (gpt-5.1) and STORY_GEMINI_MODEL (gemini-3.8-flash): the two real model knobs. Keep.
- STORY_LLM_FALLBACK_MODEL: set on service and worker in both environments. Reads are only in the non-direct branch, so it is unreachable under `direct`. Safe to delete. Residual: `worker.py` uses it as a diagnostics label when a fallback is flagged.
- Not set anywhere live and ignored under `direct`: STORY_AU_MODEL, COVERAGE_MODEL, DIRECTOR_MODEL, GUIDE_MODEL, SCENE_MODEL, EDIT_PLANNER_MODEL, MUSIC_PLAN_MODEL, DURATION_PLANNER_MODEL, BEDROCK_MODEL, BEDROCK_ROUTED_MODEL, STORY_AWS_REGION, STORY_ROUTE_<CAPABILITY>.
- Planner tuning at defaults: STORY_EDIT_PLANNER_{REPAIR_ATTEMPTS, MAX_TOKENS, MAX_TOKENS_CEILING}. Candidates to hardcode.

### E. Mocks / test-only (must never be set in a deployed env; none is set live)
STORY_ASSET_UNDERSTANDING_MOCK, COVERAGE_MOCK, CREATIVE_INTENT_MOCK, DIRECTOR_MOCK, GUIDE_MOCK, SCENE_UNDERSTANDING_MOCK, STORY_WORKER_ALLOW_TEST_DELAY.

### F. iOS configuration
- Environment identity is baked: `STORY_BUILD_ENV` + 6 `STORY_ENV_*` keys in `Config/Development.xcconfig` and `Config/Beta.xcconfig`. Verified from the files: dev points at `ydmju5wdps…` / pool AzfHOEdA5, beta at `asxtxgjiis…` / pool 3cPNfbrUl. Release builds ignore process env and fail closed on a mismatch (code-read, not run).
- DEBUG still uses the legacy chain (scheme env → UserDefaults → dev default): STORY_API_BASE_URL and STORY_COGNITO_{USER_POOL_ID, APP_CLIENT_ID, DOMAIN_PREFIX, REGION, REDIRECT_URI}.
- iOS feature keys still read from env/UserDefaults: GUIDE_V2, SCENE_IMAGES, EDITORIAL_TYPE_V2, MULTIMODAL_PLANNING, CRITIQUE_REVISION, CRITIQUE_EXPLORE, CREATIVE_REFINEMENT (7 toggles), plus REFERENCE_MEDIA_MODE, DIAG_BEACONS, STORY_APPLE_SIGNIN_AVAILABLE.
- Owner's uncommitted `Story.xcscheme` (not modified by this audit) carries 7 enabled auth/API rows, 4 disabled beta duplicates, GUIDE_V2=1, SCENE_IMAGES=1, REFERENCE_MEDIA_MODE=image. Because every accepted feature now defaults ON in code, GUIDE_V2 and SCENE_IMAGES rows are redundant.
- Build provenance: Xcode Cloud now stamps `GitCommitSHA` into Info.plist (`ci_scripts/ci_pre_xcodebuild.sh`). Local Xcode builds still report `unknown` unless passed `GIT_COMMIT_SHA`.

### G. CDK / CI knobs
- Behaviour-changing CDK context keys (10): editPlanVersion, editplanV2, editplanV2Flags, evidencePersist, guideV2, sceneImages, referenceMedia, modelProvider, openaiModel, geminiModel. `editplanV2` and `editplanV2Flags` still overlap.
- Both deploy workflows still pass `-c editplanV2=true`. #103–#106 added `--build-arg BUILD_SHA=$SHA` to both (provenance, not config).
- The service never receives the three EDITPLAN flags; only the worker does. Any sync planner path would plan under different rules.
- `deploy-beta.yml` sets REQUIRE_AUTH, QUOTA and THROTTLE explicitly; `deploy-dev.yml` leaves them at the CDK default (observe).
- CDK comment at `infrastructure/cdk/lib/story-api-stack.ts:544-545` still tells readers to pair persistence with the iOS flag `STORY_REUSABLE_EVIDENCE`. That flag no longer exists. Stale comment, no env var.

## 4. What changed since Audit 2, and what it supersedes

| Change | Source | Effect on Audit 2 |
|---|---|---|
| iOS `STORY_REUSABLE_EVIDENCE` gate removed; cache-hit reuse is now always on, cache miss runs the frame mapper guided by AU candidates (selection rule follows the attempt's editorial type). Backend persist flag unchanged. | #102 (71bc307) | **Resolves Audit 2's headline finding** (persist-but-never-reuse, Incident B). Decision 2 in Audit 2 is closed. iOS product-feature toggles drop from 8 to 7. |
| Over-long plans are fit to the requested duration; planner provenance recorded in `diag["duration_fit"]`. | #103, #105 | No env var added. |
| New build provenance: `BUILD_SHA` file in the API image and worker zip, read by `observability.build_sha()`; Xcode Cloud stamps Info.plist. | #103–#106 | Satisfies the "provenance baked into the artifact" rule. Not an env var. Makes the post-deploy "API build / worker revision" check possible without AI inference. |
| Customize versions fix, Full Story on new versions, lost job-reply recovery. | #104, #106 | No env var added. |
| Dev API image moved from e10ebaf-era to #105; beta API at #106. | deploys | Audit 2's "image digest not mapped" gap is closed for the API images (see §1). Worker still unmapped. |

Unchanged from Audit 2: no new product-feature env var was added by #102–#106. Live env value sets for dev and beta are the same as Audit 2.

## 5. Counts (measured live today)

| Metric | Now | After proposed deletions |
|---|---|---|
| Service env vars (dev = beta) | 33 | 29 (drop GUIDE_V2, SCENE_IMAGES, LLM_FALLBACK_MODEL, JOBS_API_ENABLED) |
| Worker env vars (STORY_* only) | 15 | 11 (drop 3 EDITPLAN flags and LLM_FALLBACK_MODEL; EDIT_PLAN_VERSION stays as the rollback) |
| iOS product-feature toggles | 7 | 0–2 |
| Experimental / debug switches reachable in release | CRITIQUE_EXPLORE, DIAG_BEACONS | owner decision |
| Dead entries live today | LLM_FALLBACK_MODEL ×2 (service, worker) per env | 0 |
| Code-only env reads to remove | ~17 (per-stage models, Bedrock ids, ROUTE_*, planner tuning) | 0 |

Worker projection correction: Audit 2 said 15 → 10, which was an arithmetic error. Removing the 3 EDITPLAN flags and LLM_FALLBACK_MODEL gives 15 → 11, not 10. Audit 2's arithmetic was off by one. Nothing here has been implemented, so these are projections.

## 6. Open items and owner decisions

1. STORY_EVIDENCE_PERSIST_ENABLED: keep as a server-side privacy kill-switch (recommended; beta stores testers' personal frames, account deletion still design-only) or remove.
2. Acceptance status of CRITIQUE_REVISION, CREATIVE_REFINEMENT, CRITIQUE_EXPLORE and EXCLUDE_DEFAULT_CREATIVE (USEFUL_RANGE_SOFT is already removed). Owner direction 2026-11-12: keep CRITIQUE_REVISION and CREATIVE_REFINEMENT behavior with no permanent toggle once regression tests confirm it; keep CRITIQUE_EXPLORE and EXCLUDE_DEFAULT_CREATIVE disabled by hardwiring the OFF behavior; delete the env readers.
3. Is the sync edit-plan path retired? If yes, delete JOBS_API_ENABLED and end the service/worker flag asymmetry.
4. Flip the code default of STORY_MODEL_PROVIDER to `direct` and STORY_EDIT_PLAN_VERSION to 5.3 so a non-CDK run cannot reach restricted Anthropic or an old planner.
5. Branch: `fix/prebeta-release-config-gates` still has zero commits. The main worktree holds the owner's uncommitted `project.pbxproj`, `Story.xcscheme` and `StoryHomeView.swift`, so a checkout needs coordination first.

## 7. Not verified in this audit
- Worker build SHA (BUILD_SHA is inside the zip) and whether it matches the API image on either side.
- iOS release-build behaviour on a device (fail-closed mismatch, feature defaults); this is from reading source.
- That the dev API will behave identically after it picks up #106.
- How a release build sets `STORY_APPLE_SIGNIN_AVAILABLE` (default "0").
