# P1-G0 — Configuration Inventory & Ownership (Stage A)

**Status: STAGE A (inventory + findings + recommendations) — OFFLINE, no code behavior changed, not merged, not deployed.**
Branch `fix/prebeta-release-config-gates` off master `7797b13`. Beta runtime untouched. Signing/scheme preserved.

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
