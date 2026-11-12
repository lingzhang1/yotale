# P1-G0 — Pre-beta environment cleanup: result

Branch `fix/prebeta-release-config-gates` (from master `807e1a3`; baseline = Audit 3 in
`p1g0-config-inventory.md`, master `2d2d379`). **Implemented and offline-tested. Not merged, not deployed, nothing
runtime-verified from this branch.** Every count below is measured (script in the session; method: extract
`807e1a3`, count both trees identically; env counts from `cdk synth` output).

## 1. What changed, by category

| Class | Treatment |
|---|---|
| A product defaults | Accepted behavior is code. 7 release switches deleted (below). |
| B env identity | Unchanged. Cross-checked, not copied: API/Cognito pair vs `Config/<Env>.xcconfig`. |
| C operational | Kept. Beta/gamma/prod policy now defined **once in CDK** (was also a duplicate in `deploy-beta.yml`). |
| D AI routing | One table (`packages/model_gateway/provider.py`), default provider **direct**, Anthropic/Bedrock refused. |
| E diagnostics | `STORY_DIAG_BEACONS` + `GET /health?music=` replaced by a local `os_log` (no network, no switch). |
| F rollback | One mechanism: `release/release.json` `planner.emergency_override` + `approved_overrides`. |

## 2. Deleted (exact)

**Deployed environment variables — service (6):** `STORY_JOBS_API_ENABLED`, `STORY_EDIT_PLAN_VERSION`,
`STORY_LLM_FALLBACK_MODEL`, `STORY_MODEL_PROVIDER`, `STORY_GUIDE_V2`, `STORY_SCENE_IMAGES`.
**Worker (6):** `STORY_EDIT_PLAN_VERSION`, `STORY_LLM_FALLBACK_MODEL`, `STORY_MODEL_PROVIDER`,
`STORY_EDITPLAN_OBJECTIVE_DIRECTIVES`, `STORY_EDITPLAN_BEST_VALID_RETENTION`, `STORY_EDITPLAN_APPROX_DURATION_SOFT`.

**Code-only readers (never set anywhere):** `STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE` (hard-wired to its fail-safe:
an unmarked exclude is SAFETY), `STORY_AU_MODEL`, `STORY_COVERAGE_MODEL`, `STORY_DIRECTOR_MODEL`,
`STORY_GUIDE_MODEL`, `STORY_SCENE_MODEL`, `STORY_EDIT_PLANNER_MODEL`, `STORY_MUSIC_PLAN_MODEL`,
`STORY_DURATION_PLANNER_MODEL`, `STORY_ROUTE_<CAPABILITY>` (dynamic), `STORY_BEDROCK_ROUTED_MODEL`,
`STORY_BEDROCK_MODEL`, `STORY_EDIT_PLANNER_REPAIR_ATTEMPTS`, `STORY_EDIT_PLANNER_MAX_TOKENS`,
`STORY_EDIT_PLANNER_MAX_TOKENS_CEILING` (the last three are now named constants with identical values).
(`STORY_EDITPLAN_USEFUL_RANGE_SOFT` was already gone; Audit 3 listed it wrongly.)

**iOS (7):** `STORY_EDITORIAL_TYPE_V2`, `STORY_GUIDE_V2`, `STORY_SCENE_IMAGES`, `STORY_MULTIMODAL_PLANNING`,
`STORY_CRITIQUE_EXPLORE` (hard-wired OFF), `STORY_CREATIVE_REFINEMENT` (always on), `STORY_DIAG_BEACONS` — env readers
**and** their UserDefaults override paths and setters. `STORY_APPLE_SIGNIN_AVAILABLE` moved from a launch-config
value to a baked value (relocated, not deleted).

**CDK context keys (5):** `guideV2`, `sceneImages`, `editplanV2`, `editplanV2Flags`, `modelProvider`.
**Workflow args (2):** `-c editplanV2=true` in dev and beta. **Workflow env (4 lines):** beta
`STORY_QUOTA_MODE/THROTTLE_MODE/USER_DAILY_GENS/USER_MONTHLY_USD` (moved into CDK defaults, same values).

## 3. Retained, with reason

| Setting | Where | Why |
|---|---|---|
| `STORY_CRITIQUE_REVISION` | iOS env + UserDefaults | **Owner decision**: kept for latency optimisation. Default ON. Decision logic extracted to `critiqueApplies(...)` and unit-tested. |
| `STORY_REFERENCE_MEDIA_MODE` | CDK/service + iOS | Parked video reference feature; `image` is required by `release.json`. |
| `STORY_EVIDENCE_PERSIST_ENABLED` | CDK/service | **Operational privacy kill-switch**, not a product flag. Beta stores personal frames; account deletion is still design-only. OFF = graceful full re-analysis, and the gate rejects it unless `approved_degradations` lists it. |
| `STORY_OPENAI_MODEL`, `STORY_GEMINI_MODEL` | CDK API + worker | The only provider knobs; gate requires API == worker and rejects Anthropic ids. |
| `STORY_REQUIRE_AUTH`, `STORY_QUOTA_*`, `STORY_THROTTLE_MODE`, `STORY_WORKER_DEADLINE_S` | CDK | Genuine security/cost/ops controls. Values unchanged. |
| `STORY_MODEL_PROVIDER` (reader only) | `provider.py` | Default `direct`; `bedrock` is an explicit non-release opt-in; unknown values raise. **Forbidden in any deployment** by the gate. |
| iOS `STORY_API_BASE_URL`/`STORY_COGNITO_*` | Debug builds only | Existing developer re-pointing chain (`StoryEnvironment`); Release/Beta builds ignore it (baked, fail-closed). Not touched. |
| Cognito/table/bucket/queue identities, music (`STORY_MUSIC_PROVIDER`, `STORY_EPIDEMIC_MODE`) | CDK | Environment identity / licensed integration. |

**New entries (honest accounting):** `release/release.json` (43 lines of *intent*, not a flag list); CDK optional
~~override contexts `quotaMode`/`throttleMode`~~ (added, then **removed** in the integration review: no concrete need; posture is fixed per environment in CDK);
iOS `StoryAppleSignInAvailable` Info.plist key + `STORY_APPLE_SIGNIN_AVAILABLE` xcconfig value (replaces an
Xcode-run flag).

## 4. Experimental-flag disposition

| Flag | Result | Evidence |
|---|---|---|
| `STORY_CRITIQUE_REVISION` | **kept** (owner) | New test: original Create + full re-edit → critique; Explore, targeted Revise, text-only, or setting off → none. |
| `STORY_CREATIVE_REFINEMENT` | always on, switch removed | Was default ON; deterministic, no model call, no-op when nothing to improve; existing `CreativeRefinementV2bTests` (9) unchanged. |
| `STORY_CRITIQUE_EXPLORE` | hard-wired OFF, reader removed | Behavior identical (default was OFF). Experimental code path not activated. |
| `STORY_EDITPLAN_USEFUL_RANGE_SOFT` | already removed | `test_useful_range_outside_is_never_a_hard_error`. |
| `STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE` | removed, fail-safe hard-wired | It could only make exclude handling *less* strict; unset in dev/beta. |

## 5. Synchronous EditPlan / jobs flag

iOS `StoryCreationCoordinator` holds an `EditPlanning` (sync) planner but **never calls it**; create, revise and
explore all go through `EditPlanJobClient`. So `STORY_JOBS_API_ENABLED` (default `1`, set `1` everywhere) is removed.
The sync endpoints `/v1/edit-plan` and `/v1/edit-plan-mm` are **kept** (installed older beta clients are unverified);
because `OBJECTIVE_DIRECTIVES`/`BEST_VALID_RETENTION`/`APPROX_DURATION_SOFT` are now permanent code, the sync path can
no longer diverge from the worker. Recommend retiring them in a separate change once no client < this build is in use.

## 6. Provider safety

`STORY_LLM_FALLBACK_MODEL` was unreachable under `direct`; its readers (`deps._gateway_with_fallback`, two worker
builders) are deleted. `STORY_MODEL_PROVIDER` code default is now `direct`; the shared `provider_mode()` raises on any
unknown value, and API and worker use the **same** `routed_gateway`. Worker diagnostics `model_id` now comes from
the served model or the active route (`gpt-5.1`/`gemini-3.8-flash`), never an Anthropic label. Fallback policy
(policy/access denials do not fail over) is unchanged and its existing tests pass. No Anthropic call was made.

## 7. EditPlan v5.3 default and rollback

Code default `_EDIT_PLAN_DEFAULT = "5.3"` (was `"5"`). A normal deployment emits no version variable. Rollback:

1. **Preferred — redeploy the previous immutable artifacts.** Images are pinned by digest (`release-manifests/*.json`
   and the ECR tag `git-<sha12>`); the worker zip is reproducible from its commit (`BUILD_SHA` inside). Re-run the
   deploy workflow from the last good commit/ref.
2. **Planner-only** (when the whole artifact is fine): in **one reviewed PR** set
   `release/release.json` `planner.emergency_override: "5.2"` and add
   `{"setting":"STORY_EDIT_PLAN_VERSION","env":"<env>","value":"5.2","approved_by":"…","reason":"…"}` to
   `approved_overrides`, then deploy. CDK pins **API and worker identically on every deploy** until the override is
   cleared, so a later deploy cannot silently undo it. The gate rejects: an override with no approval, API≠worker, a
   manifest rollback the deployment failed to apply (`rollback_not_applied`), a missing prompt bundle.
   Observable via the job `prompt_version` (`edit_plan/5.2`) and the post-deploy gate. Clearing = a second PR.
3. Pending jobs: prompts are versioned directories (`prompts/edit_plan/2…5.3-cand` all kept); a job resolves the
   version at execution, so in-flight jobs finish on whichever bundle the worker holds.

## 8. Gates

* **Pre-deploy** `python3 scripts/release_config_gate.py pre`: runs in CI (new job `release-config-gate`) **and** in
  `deploy-dev.yml`/`deploy-beta.yml` between the worker-asset build and `cdk deploy`, on the *synthesized* template
  with the *same* CDK context the deploy then uses (written once to `CDK_CTX`). Checks: required settings,
  duplicate/removed/unknown settings, mock switches, Anthropic/Bedrock identifiers, API↔worker agreement, planner
  default vs manifest, rollback approval, prompt assets (repo + worker zip), `BUILD_SHA` present and clean, per-env
  auth/quota/throttle/$-limit policy, evidence persistence, required capabilities, environment/identity mixing
  (incl. Cognito pair vs xcconfig), iOS xcconfig identity + explicit baked Apple flag, tracked schemes carry no
  feature switch / hand-set identity / duplicate active keys.
* **Post-deploy** `… post` (read-only AWS: App Runner, Lambda, ECR): service `RUNNING` (waits out
  `OPERATION_IN_PROGRESS`), pinned digest (== expected), image tagged `git-<expected sha>`, **deployed worker zip
  `BUILD_SHA` == expected** (downloaded via the presigned code URL and read in memory), bundled prompt for the effective
  planner, and the **live** env judged by the same rules. AWS denial/SSO expiry = **FAIL** (exit 2).
* The existing `verify-required-secrets.sh` is reused and now also runs in the dev workflow.
* **Honest limits:** the API image's `BUILD_SHA` file is verified through its `git-<sha>` tag (same workflow step passes
  both) rather than by pulling the image. "Effective planner version" is derived from the live env + the code default
  (no endpoint reports it). No diagnostics endpoint was added (§17: prefer AWS inspection), so there is no
  "unauthorized diagnostics access" to test beyond fail-closed AWS denial. The deploy roles' IAM may lack
  `apprunner:DescribeService`/`lambda:GetFunction`/`ecr:DescribeImages`; if so the post step fails until granted — an IAM
  change that needs approval.
* **Dev/beta parity rules:** product behavior identical (no switches exist); allowed differences are exactly the
  `release.json` `environments` block (auth, quota/throttle mode, $ limit, xcconfig). Gamma/production entries require
  auth + enforce and assert nothing else — **their runtime was not inspected** and no values were invented.

## 9. Apple Sign In (release build)

Neither the dev pool `us-east-1_AzfHOEdA5` nor the beta pool `us-east-1_3cPNfbrUl` has a `SignInWithApple` identity
provider (beta client supports only `COGNITO`), and there is no entitlements file. The flow is Cognito hosted web
OAuth with `identity_provider=SignInWithApple`, so it cannot work today. Previously availability was an Xcode Run
argument defaulting OFF (and was not even persisted). Now it is **baked per xcconfig (`0` in both)**; the gate requires
an explicit `0/1` and, for `1`, a live check that the IdP exists on that pool. Not hard-coded ON. Enabling it needs the
Apple IdP provisioned in the auth stack (a separate approval).

## 10. Owner migration plan for the uncommitted `Story.xcscheme`

Your working-tree scheme, `project.pbxproj` and the `StoryHomeView.swift` trailing-space hunk were **not touched or
staged**. The *committed* `Story` scheme was cleaned (it pointed the default Run at **beta** and set
`STORY_GUIDE_V2/SCENE_IMAGES`). Consequences and steps:

1. Until you pull this branch nothing changes for you.
2. Daily dev: scheme **Story** → Development.xcconfig (dev backend), no env rows needed.
   Beta testing: scheme **Story (Beta)** (already tracked; Beta configuration, baked + fail-closed).
3. When you merge/pull, git will report your modified `Story.xcscheme` conflicts. Run:
   `git stash push -- apps/ios/Story/Story.xcodeproj/xcshareddata/xcschemes/Story.xcscheme`, pull, then re-apply only your
   two intentional edits (tests `skipped = "YES"`, and `STORY_REFERENCE_MEDIA_MODE=image` — optional; the default is
   already `image`). Do **not** restore the beta identity rows or `STORY_GUIDE_V2/SCENE_IMAGES`.
4. `project.pbxproj` (signing `DEVELOPMENT_TEAM`) is independent; keep it local or commit it deliberately.

## 11. Measured counts

| Metric | Before (`807e1a3`) | After | Note |
|---|---|---|---|
| Service env vars (synth) | 33 | **27** | −6 deleted |
| Worker `STORY_*` env vars (synth) | 15 | **9** | −6 deleted (plus `PYTHONPATH`, unchanged) |
| Backend distinct `STORY_*` names read | 50 | **36** | −14; read sites 74 → 49 |
| CDK `STORY_*` textual references | 71 | **55** | |
| CDK `tryGetContext` keys | 17 | **12** | −5 removed; none added (`quotaMode`/`throttleMode` dropped in review) |
| iOS env/launch-config names read | 13 | **7** | 6 are Debug-only identity keys + the retained `STORY_CRITIQUE_REVISION` |
| iOS product-feature switches | 7 | **1** (`CRITIQUE_REVISION`, retained by owner) | + parked `REFERENCE_MEDIA_MODE` |
| Workflow beta `STORY_*` env lines | 4 | **0** | moved into CDK defaults |
| `-c editplanV2=true` args | 2 | **0** | |
| Experimental/debug switches in release config | 3 (`DIAG_BEACONS`, `CRITIQUE_EXPLORE`, `MULTIMODAL` kill-switch) | **0** | |
| Obsolete/stale entries | `STORY_LLM_FALLBACK_MODEL` (dead; set in 4 places) + 15 never-set code-only readers | **0** | all rejected by the gate if reintroduced |
| New | — | `release/release.json` (43 lines), gate script (570 lines), 37 gate tests | |

Net: 12 fewer deployed variables, 14 fewer backend reads, 6 fewer iOS reads; 0 product-feature flags except the
owner-retained critique lever.

## 12. Test results (this branch)

* Backend `pytest` (repo root): **828 passed** (baseline 794; net +34: 37 new gate tests and a few provider tests added, obsolete flag-only tests removed).
* CDK `jest`: **72 passed** (baseline 67). `tsc --noEmit` clean.
* Gate against the **real synthesized** dev and beta templates + tracked schemes: ACCEPTED.
* Gate **post** mode, read-only, against the **currently running** dev and beta: correctly REJECTS only the removed
  settings that are still live (14 violations each), and passes digest/tag/worker-`BUILD_SHA`/policy/evidence checks —
  closing Audit 3's "worker build SHA parity" gap for dev (`29f7f2f1ca02`) and beta (`2d2d379998be`).
* iOS: new `ReleaseConfigDefaultsTests` + adapted tests. **Not run.** `xcodebuild` in this sandbox fails on the Swift
  macro plugin (`Observable`/`State`/`SwiftData`), and no error references a symbol changed here. `swiftc -parse` is
  clean for every changed file — that is **not** a successful Xcode build. **Needs your device Xcode build and ⌘U.**
* CI cannot be run locally; `ci.yml`, `deploy-*.yml` parse as YAML.

## 13. CDK diff (read-only, current digest, pipeline flags incl. `observability=true`)

Dev and beta: only `EditPlanWorker` (code asset + 6 env vars removed) and `StoryApiService` (6 env vars removed). No
resource replaced or destroyed; observability, WAF, auth, tables, buckets, queues and quota/throttle values unchanged.

## 14. Remaining decisions / blockers

1. Device build + ⌘U of the iOS changes (SwiftData-touching ⇒ your Xcode build is authoritative).
2. Deploy-role IAM for the post-deploy read calls (above).
3. Retire sync `/v1/edit-plan*` once no older client remains.
4. Apple IdP provisioning (only if Apple Sign In is wanted for beta).
5. ~~quotaMode/throttleMode~~ resolved: removed.
6. Gamma/production runtime not inspected; `release.json` only states required security posture.

## 15. Integration review addendum (final)

* **quota/throttle switches:** removed. Posture is `observeOnly ? observe : enforce` (dev/test observe; beta, gamma,
  production enforce); a CDK test proves neither shell env nor context can relax beta.
* **Gate now guards the exact artifact:** both deploy workflows synthesize once into `$RUNNER_TEMP/cdk-pre`, run the
  gate on *that* template, and `cdk deploy --app $RUNNER_TEMP/cdk-pre` deploys *that assembly* (verified read-only with
  `cdk diff --app`). No second synth, no `CDK_CTX`, nothing optional to omit. Bootstrap is sound: the pre gate judges
  only the new template; the post gate runs after deploy, so the old configuration being removed is never a blocker.
* **Deploy-role IAM (live, via `iam simulate-principal-policy` on `story-{development,beta}-github-deploy`):**
  `apprunner:ListServices`, `apprunner:DescribeService` (service ARN), `lambda:GetFunction` (worker), `ecr:DescribeImages`
  (`story-<env>-api`) are all **allowed** on both. The worker-zip download uses the presigned URL from `GetFunction`
  (no extra grant). `cognito-idp:ListIdentityProviders` is denied but only needed if Apple sign-in is ever baked `1`.
  **No IAM change required now.**
* **IAM drift (report only):** the live OIDC trust is `repo:lingzhang1@*/yotale@*:environment:<env>` but
  `story-api-stack.ts` still says `lingzhang1*/story*`. Unchanged by this work; if that role resource is ever re-applied
  from source it would break GitHub OIDC for the renamed repo. Proposed fix (needs approval): update the trust pattern
  in IaC to `lingzhang1@*/yotale@*`.
* **Provider bypass found (pre-existing, not changed):** `POST` revision-interpret (`main.py` ~1071/1093) and the
  non-direct creative-intent path use `deps.get_model_gateway()`, a fixed Bedrock gateway on `amazon.nova-lite-v1:0`
  (not Anthropic) that ignores provider mode. Re-routing it is a provider-routing change → owner decision.
* **Behavior preservation:** async (iOS) path unchanged — dev/beta workers already ran the three formerly-flagged
  behaviors ON, and the old flags-ON tests pass unchanged with no env. Only the *sync* `/v1/edit-plan*` path changes
  (it now matches the worker: objectives not terminal, best-valid retention, ≤1 repair). No new repair loop; Revise ≤1
  only for an unrenderable hard defect. Soft creative misses ship a playable video with disclosure (existing tests).
  iOS critique rule is pinned by `critiqueApplies` tests (not run — see device checklist).
* **Rollback verified (executed in fresh interpreters, now tests):** no env → `edit_plan/5.3`, v5.3 evidence on,
  provider `direct`; `STORY_EDIT_PLAN_VERSION=5.2` → `edit_plan/5.2`, v5.3 evidence stripped; `STORY_MODEL_PROVIDER=anthropic`
  raises. Manifest ships with no override/degradation.
* **Final CDK diffs (read-only, real digests, pipeline flags incl. `observability=true`):** dev and beta each change
  exactly `EditPlanWorker` and `StoryApiService` in place; nothing else; no IAM/Cognito/WAF/storage/queue/observability/
  budget change; no quota/throttle/auth/evidence value changes.
* Device checklist: `p1g0-device-acceptance.md` (NOT RUN).
