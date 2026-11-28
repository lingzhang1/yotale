"""P1-G0 release configuration gate: acceptance + the mandatory NEGATIVE tests.

Every test builds a fully-correct configuration Snapshot, introduces exactly ONE defect, and asserts the gate
REJECTS it with the specific violation code. CI runs this file (pytest apps/api/tests), so a gate that stopped
rejecting a bad deployment would fail the build.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("release_config_gate", REPO / "scripts" / "release_config_gate.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules["release_config_gate"] = gate
_spec.loader.exec_module(gate)

COMMITTED = gate.load_manifest()


def _without_beta_pin(m: dict) -> dict:
    """The committed manifest minus its time-boxed beta planner pin. Most tests below model a beta that follows the
    default planner (5.3); the committed beta pin has its own dedicated tests."""
    per = {k: v for k, v in (m["planner"].get("environment_overrides") or {}).items() if k != "beta"}
    return {**m, "planner": {**m["planner"], "environment_overrides": per},
            "approved_overrides": [o for o in m["approved_overrides"] if o["env"] != "beta"]}


MANIFEST = _without_beta_pin(COMMITTED)
XC = {n: gate.parse_xcconfig(REPO / "apps/ios/Story/Config" / f"{n}.xcconfig") for n in ("Development", "Beta")}


def _pin(env: str) -> dict:
    """What a CORRECT deployment of `env` pins: exactly the planner version the manifest declares for it (if any)."""
    v = gate.manifest_planner_override(MANIFEST, env)
    return {"STORY_EDIT_PLAN_VERSION": v} if v else {}


def _snapshot(env: str) -> "gate.Snapshot":
    pol = MANIFEST["environments"][env]
    xc = XC["Beta" if env == "beta" else "Development"]
    svc = {
        "STORY_ENVIRONMENT": env,
        "STORY_JOBS_TABLE": f"story-{env}-edit-plan-jobs", "STORY_JOBS_QUEUE_URL": None,
        "STORY_STAGING_BUCKET": None, "STORY_MEDIA_TABLE": f"story-{env}-media",
        "STORY_MEDIA_BUCKET": None, "STORY_STORIES_TABLE": f"story-{env}-stories",
        "STORY_UNDERSTANDING_TABLE": f"story-{env}-understanding", "STORY_RATE_LIMIT_TABLE": f"story-{env}-rate-limits",
        "STORY_USER_USAGE_TABLE": f"story-{env}-user-usage", "STORY_IDENTITY_CLAIMS_TABLE": f"story-{env}-identity-claims",
        "STORY_USERS_TABLE": f"story-{env}-users",
        "STORY_COGNITO_USER_POOL_ID": xc["STORY_ENV_USER_POOL_ID"],
        "STORY_COGNITO_APP_CLIENT_ID": xc["STORY_ENV_APP_CLIENT_ID"],
        "STORY_REQUIRE_AUTH": pol["require_auth"], "STORY_QUOTA_MODE": pol["quota_mode"],
        "STORY_THROTTLE_MODE": pol["throttle_mode"], "STORY_QUOTA_USER_MONTHLY_USD": pol["user_monthly_usd"],
        "STORY_QUOTA_USER_DAILY_GENS": "500", "STORY_QUOTA_MAX_ACTIVE_JOBS": "2",
        "STORY_QUOTA_GLOBAL_MONTHLY_USD": "60", "STORY_BILLING_MODE": pol["billing_mode"],
        "STORY_OPENAI_MODEL": "gpt-5.1", "STORY_GEMINI_MODEL": "gemini-3.8-flash",
        "STORY_EVIDENCE_PERSIST_ENABLED": pol["evidence_persist"],
        **MANIFEST["required_everywhere"],
        **_pin(env),
    }
    wrk = {
        "PYTHONPATH": "/var/task:/var/task/packages", "STORY_ENVIRONMENT": env,
        "STORY_JOBS_TABLE": f"story-{env}-edit-plan-jobs", "STORY_JOBS_QUEUE_URL": None, "STORY_STAGING_BUCKET": None,
        "STORY_USER_USAGE_TABLE": f"story-{env}-user-usage", "STORY_WORKER_DEADLINE_S": "840",
        "STORY_QUOTA_MODE": pol["quota_mode"], "STORY_BILLING_MODE": pol["billing_mode"],
        "STORY_OPENAI_MODEL": "gpt-5.1", "STORY_GEMINI_MODEL": "gemini-3.8-flash",
        **_pin(env),
    }
    return gate.Snapshot(env, list(svc.items()), wrk)


def _codes(snap, manifest=MANIFEST, repo=REPO):
    v, _ = gate.check_snapshot(snap, manifest, repo)
    return {x.code for x in v}


def _with(snap, *, svc=None, wrk=None, drop_svc=(), drop_wrk=(), extra_svc=()):
    s = dict(snap.service)
    s.update(svc or {})
    for k in drop_svc:
        s.pop(k, None)
    w = dict(snap.worker)
    w.update(wrk or {})
    for k in drop_wrk:
        w.pop(k, None)
    return gate.Snapshot(snap.environment, list(s.items()) + list(extra_svc), w, snap.source)


@pytest.fixture
def tmp_repo(tmp_path):
    """A minimal throw-away repo root so we can delete prompts/xcconfigs without touching the real tree."""
    (tmp_path / "packages/edit_planner").mkdir(parents=True)
    shutil.copy(REPO / "packages/edit_planner/__init__.py", tmp_path / "packages/edit_planner/__init__.py")
    shutil.copytree(REPO / "prompts/edit_plan", tmp_path / "prompts/edit_plan")
    shutil.copytree(REPO / "apps/ios/Story/Config", tmp_path / "apps/ios/Story/Config")
    return tmp_path


# ------------------------------------------------------------------------------------------------ acceptance
@pytest.mark.parametrize("env", ["development", "beta"])
def test_correct_configuration_is_accepted(env):
    v, _ = gate.check_snapshot(_snapshot(env), MANIFEST)
    assert v == [], [str(x) for x in v]


def test_manifest_and_code_default_agree_and_prompt_exists():
    assert gate.code_default_planner_version() == MANIFEST["planner"]["version"] == "5.6"
    assert (REPO / "prompts/edit_plan/5.6/system.md").is_file()


def test_tracked_ios_configuration_is_accepted():
    v, _ = gate.check_ios(REPO)
    # The owner's UNCOMMITTED local scheme can legitimately differ in a working tree; CI sees the tracked one.
    tracked = [x for x in v if x.code not in ("ios_scheme_override", "duplicate_setting")]
    assert tracked == [], [str(x) for x in tracked]


_TPL_ENV = [{"Name": "STORY_ENVIRONMENT", "Value": "beta"}, {"Name": "STORY_JOBS_TABLE", "Value": {"Ref": "JobsTable"}}]


def _tpl(ecs_env=None, app_runner_env=None):
    res = {
        "Td": {"Type": "AWS::ECS::TaskDefinition", "Properties": {"ContainerDefinitions": [
            {"Name": "api", "Environment": ecs_env if ecs_env is not None else _TPL_ENV}]}},
        "Fn": {"Type": "AWS::Lambda::Function", "Properties": {
            "FunctionName": "story-beta-edit-plan-worker",
            "Environment": {"Variables": {"STORY_ENVIRONMENT": "beta"}}}}}
    if app_runner_env is not None:
        res["Svc"] = {"Type": "AWS::AppRunner::Service", "Properties": {"SourceConfiguration": {"ImageRepository": {
            "ImageConfiguration": {"RuntimeEnvironmentVariables": app_runner_env}}}}}
    return {"Resources": res}


def test_snapshot_from_cloudformation_template_roundtrip():
    snap = gate.snapshot_from_template(_tpl(), "beta")
    assert dict(snap.service) == {"STORY_ENVIRONMENT": "beta", "STORY_JOBS_TABLE": None}
    assert snap.worker == {"STORY_ENVIRONMENT": "beta"}


def test_template_without_an_ecs_api_container_is_rejected():
    tpl = _tpl(); del tpl["Resources"]["Td"]
    with pytest.raises(ValueError, match="ECS api container"):
        gate.snapshot_from_template(tpl, "beta")


def test_app_runner_only_in_the_beta_overlap_and_with_the_same_env():
    assert gate.check_template_compute(_tpl(), "production") == []
    assert gate.check_template_compute(_tpl(app_runner_env=_TPL_ENV), "beta") == []
    codes = {x.code for x in gate.check_template_compute(_tpl(app_runner_env=_TPL_ENV), "production")}
    assert codes == {"app_runner_outside_overlap"}
    codes = {x.code for x in gate.check_template_compute(_tpl(app_runner_env=_TPL_ENV[:1]), "beta")}
    assert codes == {"overlap_env_mismatch"}


# ------------------------------------------------------------------------------- mandatory negative tests
def test_N01_api_5_3_worker_5_2_is_rejected():
    s = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "5.3"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.2"})
    assert "planner_mismatch" in _codes(s)


def test_N02_required_5_6_prompt_missing_is_rejected(tmp_repo):
    shutil.rmtree(tmp_repo / "prompts/edit_plan/5.6")
    assert "prompt_missing" in _codes(_snapshot("beta"), repo=tmp_repo)
    # ...and the worker ASSET check rejects a zip root lacking the bundled prompt.
    asset = tmp_repo / "asset"
    (asset / "prompts/edit_plan/5.2").mkdir(parents=True)
    (asset / "prompts/edit_plan/5.2/system.md").write_text("x")
    (asset / "BUILD_SHA").write_text("abc")
    assert any(x.code == "prompt_missing" for x in gate.check_worker_asset(asset, _snapshot("beta"), MANIFEST))


def test_N03_restricted_bedrock_anthropic_default_is_rejected():
    s = _with(_snapshot("beta"), svc={"STORY_MODEL_PROVIDER": "bedrock",
                                      "STORY_LLM_FALLBACK_MODEL": "us.anthropic.claude-sonnet-4-6"},
              wrk={"STORY_LLM_FALLBACK_MODEL": "us.anthropic.claude-sonnet-4-6"})
    codes = _codes(s)
    assert {"removed_setting", "restricted_provider"} <= codes


def test_N03b_an_anthropic_model_id_in_a_model_selector_is_rejected():
    s = _with(_snapshot("beta"), svc={"STORY_OPENAI_MODEL": "us.anthropic.claude-opus-4-6-v1"})
    assert "restricted_provider" in _codes(s)


def test_N04_evidence_persistence_unexpectedly_off_is_rejected_unless_degradation_is_approved():
    s = _with(_snapshot("beta"), svc={"STORY_EVIDENCE_PERSIST_ENABLED": "0"})
    assert "evidence_persist_off" in _codes(s)
    approved = dict(MANIFEST, approved_degradations=[{"env": "beta", "capability": "evidence_persist",
                                                      "approved_by": "owner", "reason": "privacy hold"}])
    v, warn = gate.check_snapshot(s, approved)
    assert "evidence_persist_off" not in {x.code for x in v}
    assert any("DEGRADED" in w for w in warn), "an approved degraded state must still be reported"


def test_N05_beta_authentication_disabled_is_rejected():
    assert "auth_policy" in _codes(_with(_snapshot("beta"), svc={"STORY_REQUIRE_AUTH": "0"}))


def test_N06_beta_quota_or_throttle_observe_is_rejected():
    assert "quota_policy" in _codes(_with(_snapshot("beta"), svc={"STORY_QUOTA_MODE": "observe"}))
    assert "throttle_policy" in _codes(_with(_snapshot("beta"), svc={"STORY_THROTTLE_MODE": "observe"}))
    # a worker that settles in observe while the API enforces is also a policy hole
    assert "quota_policy" in _codes(_with(_snapshot("beta"), wrk={"STORY_QUOTA_MODE": "observe"}))


def test_N07_dev_api_paired_with_beta_cognito_is_rejected():
    s = _with(_snapshot("development"), svc={"STORY_COGNITO_USER_POOL_ID": XC["Beta"]["STORY_ENV_USER_POOL_ID"],
                                            "STORY_COGNITO_APP_CLIENT_ID": XC["Beta"]["STORY_ENV_APP_CLIENT_ID"]})
    v, _ = gate.check_snapshot(s, MANIFEST)
    assert any(x.code == "identity_mixed" and "beta value" in x.message for x in v)


def test_N07b_beta_deployment_referencing_a_dev_resource_is_rejected():
    s = _with(_snapshot("beta"), svc={"STORY_MEDIA_TABLE": "story-development-media"})
    assert "identity_mixed" in _codes(s)
    assert "identity_mixed" in _codes(_with(_snapshot("beta"), wrk={"STORY_ENVIRONMENT": "development"}))


def test_N08_mock_ai_engine_enabled_in_a_release_is_rejected():
    for mock in ("STORY_GUIDE_MOCK", "STORY_CREATIVE_INTENT_MOCK", "STORY_SCENE_UNDERSTANDING_MOCK"):
        assert "mock_in_release" in _codes(_with(_snapshot("beta"), svc={mock: "1"})), mock
        assert "mock_in_release" in _codes(_with(_snapshot("beta"), wrk={mock: "1"})), mock


def test_N09_duplicate_and_obsolete_configuration_is_rejected():
    dup = _with(_snapshot("beta"), extra_svc=[("STORY_QUOTA_MODE", "enforce")])
    assert "duplicate_setting" in _codes(dup)
    for removed in ("STORY_GUIDE_V2", "STORY_SCENE_IMAGES", "STORY_JOBS_API_ENABLED", "STORY_EDITPLAN_BEST_VALID_RETENTION",
                    "STORY_AU_MODEL", "STORY_EDIT_PLANNER_MODEL", "STORY_REUSABLE_EVIDENCE", "STORY_MODEL_PROVIDER"):
        assert "removed_setting" in _codes(_with(_snapshot("beta"), svc={removed: "1"})), removed
        assert "removed_setting" in _codes(_with(_snapshot("beta"), wrk={removed: "1"})), removed
    assert "unknown_setting" in _codes(_with(_snapshot("beta"), svc={"STORY_BRAND_NEW_TOGGLE": "1"}))


def test_N11_missing_required_beta_release_capability_is_rejected():
    assert "capability_missing" in _codes(_with(_snapshot("beta"), drop_svc=["STORY_MUSIC_PROVIDER"]))
    assert "capability_missing" in _codes(_with(_snapshot("beta"), svc={"STORY_REFERENCE_MEDIA_MODE": "video"}))  # parked
    assert "missing_required" in _codes(_with(_snapshot("beta"), drop_svc=["STORY_USER_USAGE_TABLE"]))
    assert "missing_required" in _codes(_with(_snapshot("beta"), drop_wrk=["STORY_QUOTA_MODE"]))


def test_N13_unapproved_emergency_rollback_override_is_rejected_and_approval_unblocks_it():
    pinned = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "5.2"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.2"})
    # (a) API and worker AGREE on 5.2 but the manifest does not declare it => hand-pinned, rejected.
    assert "unapproved_override" in _codes(pinned)
    # (b) declared in the manifest but WITHOUT an approved_overrides entry => rejected.
    declared = {**MANIFEST, "planner": {**MANIFEST["planner"], "emergency_override": "5.2"}}
    assert "unapproved_override" in _codes(pinned, manifest=declared)
    # (c) declared AND approved => accepted.
    ok = {**declared, "approved_overrides": [{"setting": "STORY_EDIT_PLAN_VERSION", "env": "beta", "value": "5.2",
                                              "approved_by": "owner", "reason": "incident"}]}
    assert _codes(pinned, manifest=ok) == set()
    # (d) approval for a DIFFERENT environment does not cover beta.
    wrong_env = {**declared, "approved_overrides": [{"setting": "STORY_EDIT_PLAN_VERSION", "env": "development", "value": "5.2"}]}
    assert "unapproved_override" in _codes(pinned, manifest=wrong_env)
    # (e) a later deploy that silently DROPS a declared rollback is rejected.
    assert "rollback_not_applied" in _codes(_snapshot("beta"), manifest=ok)
    # (f) a rollback to a version with no prompt bundle is rejected even when declared+approved.
    s9 = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "9.9"}, wrk={"STORY_EDIT_PLAN_VERSION": "9.9"})
    ok9 = {**MANIFEST, "planner": {**MANIFEST["planner"], "emergency_override": "9.9"},
           "approved_overrides": [{"setting": "STORY_EDIT_PLAN_VERSION", "env": "beta", "value": "9.9"}]}
    assert "prompt_missing" in _codes(s9, manifest=ok9)


def test_committed_manifest_has_no_stage_drift():
    """Stage parity guard. Every stage runs the same planner (the default) and declares the same evidence persistence. The
    committed manifest carries no per-environment planner pin and no global rollback; any future pin must be time-boxed."""
    pl = COMMITTED["planner"]
    assert pl["emergency_override"] is None, "no GLOBAL planner override may be committed"
    assert not (pl.get("environment_overrides") or {}), "no per-environment planner pin may be committed"
    for env in COMMITTED["environments"]:
        assert gate.manifest_planner_override(COMMITTED, env) is None, env
    assert gate.check_stage_parity(COMMITTED) == []
    assert {p.get("evidence_persist") for p in COMMITTED["environments"].values()} == {"1"}
    for o in COMMITTED["approved_overrides"]:
        assert o.get("approved_by") and o.get("reason"), "an approval must name who and why"
        if (o["setting"], o["env"], str(o["value"])) == ("STORY_BILLING_MODE", "production", "enforce"):
            assert o.get("approved_on"), "the launch billing posture is permanent but dated"   # owner 2026-11-28
            continue
        assert o["env"] in ("development", "beta")
        assert o.get("expires"), "a time-boxed approval must say when it ends"
    assert COMMITTED["approved_degradations"] == []


def test_stage_parity_rejects_drift():
    prod_off = {**COMMITTED, "environments": {**COMMITTED["environments"],
                "production": {**COMMITTED["environments"]["production"], "evidence_persist": "0"}}}
    assert "stage_parity" in {x.code for x in gate.check_stage_parity(prod_off)}
    missing = {**COMMITTED, "environments": {**COMMITTED["environments"],
               "production": {k: x for k, x in COMMITTED["environments"]["production"].items() if k != "evidence_persist"}}}
    assert "stage_parity" in {x.code for x in gate.check_stage_parity(missing)}
    pinned = {**COMMITTED, "planner": {**COMMITTED["planner"], "environment_overrides": {"beta": "5.5"}}}
    assert "stage_parity" in {x.code for x in gate.check_stage_parity(pinned)}, "a pin without a time-boxed approval is drift"
    ok = {**pinned, "approved_overrides": [{"setting": "STORY_EDIT_PLAN_VERSION", "env": "beta", "value": "5.5",
                                            "approved_by": "owner", "reason": "eval", "expires": "2099-01-01"}]}
    assert gate.check_stage_parity(ok) == []
    assert "stage_parity" in _codes(_snapshot("beta"), manifest=prod_off), "the deploy gate itself must fail on drift"


def test_manifest_planner_override_resolution():
    m = {"planner": {"version": "5.3", "emergency_override": None}}
    assert gate.manifest_planner_override(m, "development") is None
    m = {"planner": {"version": "5.3", "emergency_override": None, "environment_overrides": {"development": "5.5"}}}
    assert gate.manifest_planner_override(m, "development") == "5.5"
    assert [gate.manifest_planner_override(m, e) for e in ("beta", "gamma", "production")] == [None, None, None]
    g = {"planner": {"version": "5.3", "emergency_override": "5.2"}}                       # global still reaches every env
    assert {gate.manifest_planner_override(g, e) for e in ("development", "beta", "production")} == {"5.2"}
    both = {"planner": {"emergency_override": "5.2", "environment_overrides": {"development": "5.5"}}}
    assert gate.manifest_planner_override(both, "development") == "5.5" and gate.manifest_planner_override(both, "beta") == "5.2"


def _dev_pin_manifest(expires="2099-01-01"):
    return {**MANIFEST,
            "planner": {**MANIFEST["planner"], "emergency_override": None, "environment_overrides": {"development": "5.5"}},
            "approved_overrides": [*[o for o in MANIFEST["approved_overrides"] if o["setting"] == "STORY_BILLING_MODE"],
                                   {"setting": "STORY_EDIT_PLAN_VERSION", "env": "development", "value": "5.5",
                                    "approved_by": "owner", "reason": "evaluation", "expires": expires}]}


def test_dev_only_pin_is_accepted_for_development_and_never_touches_beta():
    m = _dev_pin_manifest()
    dev = _with(_snapshot("development"), svc={"STORY_EDIT_PLAN_VERSION": "5.5"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.5"})
    assert _codes(dev, manifest=m) == set()
    beta = _snapshot("beta")                                              # no pin: accepted, the manifest does not pin beta
    assert "STORY_EDIT_PLAN_VERSION" not in dict(beta.service) and _codes(beta, manifest=m) == set()


def test_dev_only_pin_cannot_leak_to_beta_or_be_dropped_from_dev():
    m = _dev_pin_manifest()
    leaked = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "5.5"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.5"})
    codes = _codes(leaked, manifest=m)
    assert "unapproved_override" in codes, "a 5.5 pin on beta must be rejected even though development is approved"
    dropped = _snapshot("development")                                     # dev deploy that silently lacks the declared pin
    dropped = _with(dropped, drop_svc=["STORY_EDIT_PLAN_VERSION"], drop_wrk=["STORY_EDIT_PLAN_VERSION"])
    assert "rollback_not_applied" in _codes(dropped, manifest=m)


def test_dev_pin_is_rejected_when_the_manifest_does_not_approve_it():
    m = _dev_pin_manifest(); m["approved_overrides"] = []
    dev = _with(_snapshot("development"), svc={"STORY_EDIT_PLAN_VERSION": "5.5"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.5"})
    assert "unapproved_override" in _codes(dev, manifest=m)


def test_override_expiry(monkeypatch):
    import datetime
    dev = _with(_snapshot("development"), svc={"STORY_EDIT_PLAN_VERSION": "5.5"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.5"})
    m = _dev_pin_manifest(expires="2026-11-30")
    monkeypatch.setattr(gate, "_today", lambda: datetime.date(2026, 11, 30))       # the expiry day itself is still valid
    assert _codes(dev, manifest=m) == set()
    monkeypatch.setattr(gate, "_today", lambda: datetime.date(2026, 12, 1))
    assert "override_expired" in _codes(dev, manifest=m)
    bad = _dev_pin_manifest(expires="next week")
    assert "override_expiry_invalid" in _codes(dev, manifest=bad)


def test_environment_overrides_must_name_a_defined_environment():
    m = {**MANIFEST, "planner": {**MANIFEST["planner"], "environment_overrides": {"develpoment": "5.5"}}}
    assert "unknown_environment" in _codes(_snapshot("beta"), manifest=m)


def test_planner_default_drift_from_manifest_is_rejected(tmp_repo):
    p = tmp_repo / "packages/edit_planner/__init__.py"
    p.write_text(p.read_text().replace('_EDIT_PLAN_DEFAULT = "5.6"', '_EDIT_PLAN_DEFAULT = "5"'))
    assert "planner_default_mismatch" in _codes(_snapshot("beta"), repo=tmp_repo)


def test_api_worker_model_or_environment_disagreement_is_rejected():
    assert "api_worker_mismatch" in _codes(_with(_snapshot("beta"), wrk={"STORY_OPENAI_MODEL": "gpt-4o"}))
    assert "api_worker_mismatch" in _codes(_with(_snapshot("beta"), wrk={"STORY_GEMINI_MODEL": "gem-x"}))


def test_gamma_and_production_require_secure_policy_without_inventing_limits():
    for env in ("gamma", "production"):
        snap = _snapshot("development")
        snap = gate.Snapshot(env, [(k, v) for k, v in snap.service
                                   if k not in ("STORY_ENVIRONMENT",)] + [("STORY_ENVIRONMENT", env)],
                             dict(snap.worker, STORY_ENVIRONMENT=env))
        codes = _codes(_with(snap, svc={"STORY_COGNITO_USER_POOL_ID": "x", "STORY_COGNITO_APP_CLIENT_ID": "y"}))
        assert {"auth_policy", "quota_policy", "throttle_policy"} <= codes   # dev-style observe/auth-off is rejected
    assert "unknown_environment" in _codes(gate.Snapshot("staging", [], {}))


def test_violation_messages_never_echo_values_of_restricted_or_secret_settings():
    secret = "sk-live-SUPERSECRET-123456"
    s = _with(_snapshot("beta"), svc={"STORY_LLM_FALLBACK_MODEL": "us.anthropic." + secret, "STORY_UNSAFE_NEW": secret})
    v, warn = gate.check_snapshot(s, MANIFEST)
    assert secret not in "\n".join(str(x) for x in v) + "\n".join(warn)


# ------------------------------------------------------------------------------------------------------ iOS
def test_ios_scheme_with_removed_flags_or_hand_set_identity_is_rejected(tmp_path):
    scheme = tmp_path / "S.xcscheme"
    scheme.write_text('<Scheme><LaunchAction><EnvironmentVariables>'
                      '<EnvironmentVariable key="STORY_GUIDE_V2" value="1" isEnabled="YES"/>'
                      '<EnvironmentVariable key="STORY_API_BASE_URL" value="https://x" isEnabled="YES"/>'
                      '<EnvironmentVariable key="STORY_API_BASE_URL" value="https://y" isEnabled="YES"/>'
                      '<EnvironmentVariable key="STORY_SCENE_IMAGES" value="1" isEnabled="NO"/>'
                      '</EnvironmentVariables></LaunchAction></Scheme>')
    v, _ = gate.check_ios(REPO, scheme)
    codes = {x.code for x in v}
    assert {"ios_scheme_override", "duplicate_setting"} <= codes
    assert not any("STORY_SCENE_IMAGES" in x.message for x in v), "a DISABLED row is not an active definition"


def test_ios_xcconfig_mixing_and_unbaked_federated_providers_are_rejected(tmp_repo):
    cfg = tmp_repo / "apps/ios/Story/Config"
    beta = (cfg / "Beta.xcconfig").read_text()
    dev = (cfg / "Development.xcconfig").read_text()
    (cfg / "Beta.xcconfig").write_text(re.sub(r"STORY_ENV_USER_POOL_ID = .*", "STORY_ENV_USER_POOL_ID = "
                                              + XC["Development"]["STORY_ENV_USER_POOL_ID"], beta))
    v, _ = gate.check_ios(tmp_repo)
    assert any(x.code == "ios_identity" and "share STORY_ENV_USER_POOL_ID" in x.message for x in v)
    (cfg / "Beta.xcconfig").write_text(beta)
    line = r"(?m)^STORY_FEDERATED_PROVIDERS = .*$"
    for bad in ("", "STORY_FEDERATED_PROVIDERS = Facebook", "STORY_FEDERATED_PROVIDERS = Google"):
        (cfg / "Development.xcconfig").write_text(re.sub(line, bad, dev))
        v, _ = gate.check_ios(tmp_repo)
        assert any(x.code == "ios_federated_providers" for x in v), bad
    for ok in ("STORY_FEDERATED_PROVIDERS = none", "STORY_FEDERATED_PROVIDERS = SignInWithApple, Google"):
        (cfg / "Development.xcconfig").write_text(re.sub(line, ok, dev))
        v, _ = gate.check_ios(tmp_repo)
        assert not any(x.code == "ios_federated_providers" for x in v), ok


def test_production_xcconfig_is_checked_and_must_not_share_beta_identity(tmp_repo):
    cfg = tmp_repo / "apps/ios/Story/Config"
    prod = (cfg / "Production.xcconfig").read_text()
    assert not any(x.code in ("ios_identity", "ios_config_missing") for x in gate.check_ios(tmp_repo)[0])
    (cfg / "Production.xcconfig").write_text(re.sub(r"STORY_ENV_APP_CLIENT_ID = .*", "STORY_ENV_APP_CLIENT_ID = "
                                                    + XC["Beta"]["STORY_ENV_APP_CLIENT_ID"], prod))
    v, _ = gate.check_ios(tmp_repo)
    assert any(x.code == "ios_identity" and "Beta and Production" in x.message for x in v)
    (cfg / "Production.xcconfig").write_text(prod.replace("STORY_BUILD_ENV = production", "STORY_BUILD_ENV = beta"))
    v, _ = gate.check_ios(tmp_repo)
    assert any(x.code == "ios_identity" and "Production.xcconfig STORY_BUILD_ENV" in x.message for x in v)
    (cfg / "Production.xcconfig").unlink()
    assert {x.code for x in gate.check_ios(tmp_repo)[0]} == {"ios_config_missing"}


def test_federated_providers_are_baked_and_not_read_from_launch_config():
    sw = (REPO / "apps/ios/Story/Story/Data/Auth/StoryAuthConfig.swift").read_text()
    assert "StoryLaunchConfig" not in sw.split("static var federatedProviders")[1].split("static var domainHost")[0]
    assert "StoryFederatedProviders" in (REPO / "apps/ios/Story/Story/Info.plist").read_text()


# --------------------------------------------------------------------------- post-deploy (live) verification
def _live(env="beta", *, sha="abc123def456", digest="sha256:" + "a" * 64, status="STABLE", worker_sha=None,
          tags=None, files=None, snapshot=None, missing_idps=None, targets=(1, 1), web_acl="arn:aws:wafv2:acl",
          overlap="same"):
    return gate.LiveInfo(
        snapshot or _snapshot(env), status, f"123.dkr.ecr.us-east-1.amazonaws.com/story-{env}-api@{digest}",
        tags if tags is not None else [f"git-{sha}"], worker_sha if worker_sha is not None else sha,
        files if files is not None else {"BUILD_SHA", "prompts/edit_plan/5.6/system.md"}, missing_idps,
        targets_total=targets[0], targets_healthy=targets[1], web_acl_arn=web_acl,
        overlap_digest=digest if overlap == "same" else overlap)


def _live_codes(info, sha="abc123def456", digest="sha256:" + "a" * 64, manifest=MANIFEST):
    v, _ = gate.check_live(info, manifest, sha, digest)
    return {x.code for x in v}


def test_live_matching_deployment_is_accepted():
    assert _live_codes(_live()) == set()


def test_N10_incorrect_worker_build_sha_is_rejected():
    assert "worker_build_sha_mismatch" in _live_codes(_live(worker_sha="deadbeef0000"))
    assert "worker_build_sha_mismatch" in _live_codes(_live(worker_sha="abc123def456-dirty"))
    no_sha = gate.LiveInfo(_snapshot("beta"), "STABLE", "r@sha256:" + "a" * 64, ["git-abc123def456"], None,
                           {"prompts/edit_plan/5.6/system.md"})
    assert "worker_build_sha_missing" in _live_codes(no_sha)


def test_live_api_image_must_match_expected_digest_and_build_sha_tag():
    assert "digest_mismatch" in _live_codes(_live(digest="sha256:" + "b" * 64), digest="sha256:" + "a" * 64)
    assert "api_build_sha_mismatch" in _live_codes(_live(tags=["git-111111111111"]))
    assert "service_not_running" in _live_codes(_live(status="DEPLOYING"))
    assert "service_not_running" in _live_codes(_live(status="UNSTABLE"))


def test_live_ecs_targets_waf_and_overlap_digest():
    assert "targets_unhealthy" in _live_codes(_live(targets=(2, 1)))
    assert "targets_unhealthy" in _live_codes(_live(targets=(0, 0)))
    assert "waf_missing" in _live_codes(_live(web_acl=None))
    assert "waf_missing" not in _live_codes(_live("development", web_acl=None, overlap=None))
    assert "overlap_digest_mismatch" in _live_codes(_live(overlap="sha256:" + "c" * 64))
    assert "overlap_digest_mismatch" not in _live_codes(_live(overlap=None))   # overlap ended


def test_live_worker_zip_must_bundle_the_effective_planner_prompt():
    assert "worker_prompt_missing" in _live_codes(_live(files={"BUILD_SHA"}))


def test_live_runtime_environment_is_judged_by_the_same_rules_as_the_template():
    bad = _with(_snapshot("beta"), svc={"STORY_REQUIRE_AUTH": "0", "STORY_GUIDE_V2": "1"})
    codes = _live_codes(_live(snapshot=bad))
    assert {"auth_policy", "removed_setting"} <= codes


def test_live_federated_provider_offered_without_idp_is_rejected():
    assert "ios_federated_providers" in _live_codes(_live(missing_idps=["Google"]))
    assert "ios_federated_providers" not in _live_codes(_live(missing_idps=[]))
    assert "ios_federated_providers" not in _live_codes(_live(missing_idps=None))


def test_N12_unauthorized_or_unreadable_deployment_state_fails_closed(monkeypatch, capsys):
    """No debug endpoint exists (diagnostics use IAM-authorized AWS reads). When AWS denies access, the gate must
    FAIL (exit 2, 'unverifiable'), never report 'accepted'."""
    def denied(args):
        raise gate.AwsUnavailable("AccessDeniedException: not authorized to perform apprunner:ListServices")
    monkeypatch.setattr(gate, "default_aws", lambda profile, region: denied)
    rc = gate.main(["post", "--environment", "beta", "--expected-sha", "abc123def456"])
    out = capsys.readouterr().out
    assert rc == 2 and "unverifiable" in out and "ACCEPTED" not in out


def test_collect_live_reads_worker_build_sha_and_prompts_from_the_deployed_zip():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BUILD_SHA", "abc123def456")
        z.writestr("prompts/edit_plan/5.6/system.md", "x")
    calls = []

    D = "sha256:" + "a" * 64

    def aws(args):
        calls.append(args[:2])
        if args[:2] == ["ecs", "describe-services"]:
            return {"services": [{"status": "ACTIVE", "desiredCount": 1, "runningCount": 1,
                                  "deployments": [{"status": "PRIMARY", "rolloutState": "COMPLETED"}],
                                  "taskDefinition": "arn:td:1", "loadBalancers": [{"targetGroupArn": "arn:tg"}]}]}
        if args[:2] == ["ecs", "describe-task-definition"]:
            return {"taskDefinition": {"containerDefinitions": [
                {"name": "api", "image": f"r/story-beta-api@{D}",
                 "environment": [{"name": "STORY_ENVIRONMENT", "value": "beta"}]}]}}
        if args[:2] == ["elbv2", "describe-target-health"]:
            return {"TargetHealthDescriptions": [{"TargetHealth": {"State": "healthy"}}]}
        if args[:2] == ["elbv2", "describe-target-groups"]:
            return {"TargetGroups": [{"LoadBalancerArns": ["arn:alb"]}]}
        if args[:2] == ["wafv2", "get-web-acl-for-resource"]:
            return {"WebACL": {"ARN": "arn:waf"}}
        if args[:2] == ["apprunner", "list-services"]:
            return {"ServiceSummaryList": [{"ServiceName": "story-beta-api", "ServiceArn": "arn:x"}]}
        if args[:2] == ["apprunner", "describe-service"]:
            return {"Service": {"Status": "RUNNING", "SourceConfiguration": {"ImageRepository": {
                "ImageIdentifier": f"r/story-beta-api@{D}"}}}}
        if args[:2] == ["lambda", "get-function"]:
            return {"Configuration": {"Environment": {"Variables": {"STORY_ENVIRONMENT": "beta"}}},
                    "Code": {"Location": "https://s3/presigned"}}
        if args[:2] == ["ecr", "describe-images"]:
            return {"imageDetails": [{"imageTags": ["git-abc123def456"]}]}
        raise AssertionError(args)

    info = gate.collect_live("beta", aws, fetch=lambda url: buf.getvalue())
    assert info.worker_build_sha == "abc123def456" and "prompts/edit_plan/5.6/system.md" in info.worker_files
    assert info.image_tags == ["git-abc123def456"] and info.service_status == "STABLE"
    assert dict(info.snapshot.service) == {"STORY_ENVIRONMENT": "beta"}
    assert (info.targets_total, info.targets_healthy, info.web_acl_arn, info.overlap_digest) == (1, 1, "arn:waf", D)
    # production never queries App Runner
    calls.clear()
    gate.collect_live("production", aws, fetch=lambda url: buf.getvalue())
    assert not any(c[0] == "apprunner" for c in calls)
    assert all(c[0] in ("ecs", "elbv2", "wafv2", "lambda", "ecr") for c in calls)   # read-only service families only


# ------------------------------------------------------------------- repo-wide: removed switches stay removed
_READER_PATTERNS = [
    r'environ(?:\.get)?\(\s*["\']{n}["\']', r'environ\[\s*["\']{n}["\']', r'getenv\(\s*["\']{n}["\']',
    r'environment\[\s*"{n}"\s*\]', r'name:\s*"{n}"', r'^\s*{n}\s*:', r'\bkey\s*=\s*"{n}"',
]


def _source_files():
    roots = [("apps/api/app", "*.py"), ("packages", "*.py"), ("infrastructure/cdk/lib", "*.ts"),
             ("apps/ios/Story/Story", "*.swift"), (".github/workflows", "*.yml")]
    for root, pat in roots:
        for p in (REPO / root).rglob(pat):
            if "tests" not in p.parts and not p.name.startswith("test_"):
                yield p


# STORY_MODEL_PROVIDER keeps exactly ONE reader: the shared provider router, where the default is "direct" and
# "bedrock" is an explicit developer/non-release opt-in. It is forbidden in every DEPLOYED environment by the gate
# (REMOVED_SETTINGS) and is not set by CDK or any workflow.
_READER_EXEMPT = {("packages/model_gateway/provider.py", "STORY_MODEL_PROVIDER")}


def test_removed_switches_have_no_readers_or_injectors_anywhere_in_product_code():
    removed = sorted(gate.REMOVED_SETTINGS)
    hits = []
    for p in _source_files():
        text = p.read_text(errors="ignore")
        for n in removed:
            if n not in text or (str(p.relative_to(REPO)), n) in _READER_EXEMPT:
                continue
            for pat in _READER_PATTERNS:
                if re.search(pat.format(n=re.escape(n)), text, re.M):
                    hits.append(f"{p.relative_to(REPO)}: {n}")
    assert not hits, "re-introduced removed release switch(es): " + "; ".join(hits)


def test_retained_ios_critique_revision_switch_is_still_present():
    """Owner decision: STORY_CRITIQUE_REVISION is deliberately kept (latency lever) - guard against a cleanup deleting it."""
    sw = (REPO / "apps/ios/Story/Story/Domain/Creation/StoryMultimodalPlanning.swift").read_text()
    assert "critiqueRevisionEnabled" in sw and 'STORY_CRITIQUE_REVISION' in sw
    assert "STORY_CRITIQUE_REVISION" not in gate.REMOVED_SETTINGS and "STORY_CRITIQUE_REVISION" not in gate.IOS_FORBIDDEN_SCHEME_KEYS


def test_deploy_workflows_run_the_gate_before_and_after_deploy():
    for wf, env in (("deploy-dev.yml", "development"), ("deploy-beta.yml", "beta")):
        text = (REPO / ".github/workflows" / wf).read_text()
        assert f"release_config_gate.py pre --environment {env}" in text, wf
        assert f"release_config_gate.py post --environment {env}" in text, wf
        assert text.index("release_config_gate.py pre") < text.index("npx cdk deploy") < text.index("release_config_gate.py post"), wf
        # the deploy consumes the EXACT gated cloud assembly, never a fresh (possibly different) synth
        assert '--app "$RUNNER_TEMP/cdk-pre"' in text and "CDK_CTX" not in text, wf
        assert f"cdk synth -q -c environment={env}" in text, wf
    ci = (REPO / ".github/workflows/ci.yml").read_text()
    assert "release_config_gate.py pre" in ci


# ------------------------------------------------------------------ runtime behavior of defaults + rollback
def _probe(code: str, **env) -> str:
    import os
    import subprocess
    e = {k: v for k, v in os.environ.items() if not k.startswith("STORY_")}
    e.update(env)
    e["PYTHONPATH"] = f"{REPO}/packages:{REPO}:{REPO}/apps/api"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=e, cwd=REPO)
    return (r.stdout + r.stderr).strip()


def test_runtime_normal_deploy_selects_v56_and_direct_providers_with_no_env():
    out = _probe("import edit_planner as e; from model_gateway.provider import provider_mode as m;"
                 "print(e.PROMPT_VERSION, e._v53_active(), m())")
    assert out.splitlines()[-1] == "edit_plan/5.6 True direct"


def test_runtime_emergency_rollback_selects_v52_and_strips_v53_evidence():
    out = _probe("import edit_planner as e; print(e.PROMPT_VERSION, e._v53_active())", STORY_EDIT_PLAN_VERSION="5.2")
    assert out.splitlines()[-1] == "edit_plan/5.2 False"


def test_runtime_unknown_provider_fails_explicitly_instead_of_falling_back():
    out = _probe("from model_gateway.provider import provider_mode as m; m()", STORY_MODEL_PROVIDER="anthropic")
    assert "unsupported STORY_MODEL_PROVIDER" in out


# ------------------------------------------------------------------------------------------------ Billing V1 posture
def test_committed_manifest_billing_posture_never_unapproved_enforce():
    # Owner 2026-11-28: billing enforced in production from launch; beta observe; dev and gamma off.
    assert {e: p.get("billing_mode") for e, p in COMMITTED["environments"].items()} == {
        "development": "off", "beta": "observe", "gamma": "off", "production": "enforce"}
    approved = {(o.get("setting"), o.get("env"), str(o.get("value"))) for o in COMMITTED.get("approved_overrides", [])}
    for e, p in COMMITTED["environments"].items():
        if p.get("billing_mode") == "enforce":
            assert ("STORY_BILLING_MODE", e, "enforce") in approved


@pytest.mark.parametrize("env", ["development", "beta"])
def test_billing_mode_must_match_the_release_in_service_and_worker(env):
    # a service value that differs from the manifest (dev=off, beta=observe) and a worker value that differs too
    drift = "observe" if env == "development" else "off"
    wdrift = "enforce"
    assert "billing_policy" in _codes(_with(_snapshot(env), svc={"STORY_BILLING_MODE": drift}))
    assert "billing_policy" in _codes(_with(_snapshot(env), wrk={"STORY_BILLING_MODE": wdrift}))


@pytest.mark.parametrize("bad", ["enforced", "ON", "true", "1", ""])
def test_an_invalid_billing_mode_is_a_violation_not_silently_off(bad):
    assert "billing_policy" in _codes(_with(_snapshot("beta"), svc={"STORY_BILLING_MODE": bad}))
    assert "billing_policy" in _codes(_with(_snapshot("beta"), wrk={"STORY_BILLING_MODE": bad}))


def test_billing_mode_is_required_in_service_and_worker():
    assert "missing_required" in _codes(_with(_snapshot("beta"), drop_svc=("STORY_BILLING_MODE",)))
    assert "missing_required" in _codes(_with(_snapshot("beta"), drop_wrk=("STORY_BILLING_MODE",)))


def test_a_second_configuration_source_for_allowances_is_rejected():
    codes = _codes(_with(_snapshot("beta"), extra_svc=(("STORY_BILLING_PLANS_JSON", '{"plus":{"videos":999}}'),)))
    assert "removed_setting" in codes
    assert "removed_setting" in _codes(_with(_snapshot("beta"), wrk={"STORY_BILLING_PLANS_JSON": "{}"}))


def test_enforce_in_the_manifest_requires_an_explicit_owner_approval():
    def manifest(mode, approve):
        m = {**MANIFEST, "environments": {**MANIFEST["environments"],
                                         "beta": {**MANIFEST["environments"]["beta"], "billing_mode": mode}}}
        if approve:
            m = {**m, "approved_overrides": list(m["approved_overrides"]) + [
                {"setting": "STORY_BILLING_MODE", "env": "beta", "value": "enforce", "approved_by": "owner",
                 "approved_on": "2026-12-01", "expires": "2027-12-01", "reason": "test"}]}
        return m
    snap = _with(_snapshot("beta"), svc={"STORY_BILLING_MODE": "enforce"}, wrk={"STORY_BILLING_MODE": "enforce"})
    assert "billing_enforce_unapproved" in _codes(snap, manifest("enforce", approve=False))
    assert "billing_enforce_unapproved" not in _codes(snap, manifest("enforce", approve=True))
    # observe never needs approval; an unapproved enforce cannot be smuggled in via the running config either
    obs = _with(_snapshot("beta"), svc={"STORY_BILLING_MODE": "observe"}, wrk={"STORY_BILLING_MODE": "observe"})
    assert _codes(obs, manifest("observe", approve=False)) == set()
    assert "billing_policy" in _codes(snap, manifest("off", approve=False))
