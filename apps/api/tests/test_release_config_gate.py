"""P1-G0 release configuration gate: acceptance + the mandatory NEGATIVE tests.

Every test builds a fully-correct configuration Snapshot, introduces exactly ONE defect, and asserts the gate
REJECTS it with the specific violation code. CI runs this file (pytest apps/api/tests), so a gate that stopped
rejecting a bad deployment would fail the build.
"""
from __future__ import annotations

import importlib.util
import json
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

MANIFEST = gate.load_manifest()
XC = {n: gate.parse_xcconfig(REPO / "apps/ios/Story/Config" / f"{n}.xcconfig") for n in ("Development", "Beta")}


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
        "STORY_QUOTA_GLOBAL_MONTHLY_USD": "60",
        "STORY_OPENAI_MODEL": "gpt-5.1", "STORY_GEMINI_MODEL": "gemini-3.8-flash",
        "STORY_EVIDENCE_PERSIST_ENABLED": pol["evidence_persist"],
        **MANIFEST["required_everywhere"],
    }
    wrk = {
        "PYTHONPATH": "/var/task:/var/task/packages", "STORY_ENVIRONMENT": env,
        "STORY_JOBS_TABLE": f"story-{env}-edit-plan-jobs", "STORY_JOBS_QUEUE_URL": None, "STORY_STAGING_BUCKET": None,
        "STORY_USER_USAGE_TABLE": f"story-{env}-user-usage", "STORY_WORKER_DEADLINE_S": "840",
        "STORY_QUOTA_MODE": pol["quota_mode"], "STORY_OPENAI_MODEL": "gpt-5.1", "STORY_GEMINI_MODEL": "gemini-3.8-flash",
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
    assert gate.code_default_planner_version() == MANIFEST["planner"]["version"] == "5.3"
    assert (REPO / "prompts/edit_plan/5.3/system.md").is_file()


def test_tracked_ios_configuration_is_accepted():
    v, _ = gate.check_ios(REPO)
    # The owner's UNCOMMITTED local scheme can legitimately differ in a working tree; CI sees the tracked one.
    tracked = [x for x in v if x.code not in ("ios_scheme_override", "duplicate_setting")]
    assert tracked == [], [str(x) for x in tracked]


def test_snapshot_from_cloudformation_template_roundtrip():
    tpl = {"Resources": {
        "Svc": {"Type": "AWS::AppRunner::Service", "Properties": {"SourceConfiguration": {"ImageRepository": {
            "ImageConfiguration": {"RuntimeEnvironmentVariables": [
                {"Name": "STORY_ENVIRONMENT", "Value": "beta"},
                {"Name": "STORY_JOBS_TABLE", "Value": {"Ref": "JobsTable"}}]}}}}},
        "Fn": {"Type": "AWS::Lambda::Function", "Properties": {
            "FunctionName": "story-beta-edit-plan-worker",
            "Environment": {"Variables": {"STORY_ENVIRONMENT": "beta"}}}}}}
    snap = gate.snapshot_from_template(tpl, "beta")
    assert dict(snap.service) == {"STORY_ENVIRONMENT": "beta", "STORY_JOBS_TABLE": None}
    assert snap.worker == {"STORY_ENVIRONMENT": "beta"}


# ------------------------------------------------------------------------------- mandatory negative tests
def test_N01_api_5_3_worker_5_2_is_rejected():
    s = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "5.3"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.2"})
    assert "planner_mismatch" in _codes(s)


def test_N02_required_5_3_prompt_missing_is_rejected(tmp_repo):
    shutil.rmtree(tmp_repo / "prompts/edit_plan/5.3")
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
    s = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "5.2"}, wrk={"STORY_EDIT_PLAN_VERSION": "5.2"})
    assert "unapproved_override" in _codes(s)           # API and worker AGREE, still unapproved
    ok = dict(MANIFEST, approved_overrides=[{"setting": "STORY_EDIT_PLAN_VERSION", "env": "beta", "value": "5.2",
                                              "approved_by": "owner", "reason": "incident"}])
    assert _codes(s, manifest=ok) == set()
    # an approval for a DIFFERENT environment or value does not cover it
    wrong_env = dict(MANIFEST, approved_overrides=[{"setting": "STORY_EDIT_PLAN_VERSION", "env": "development", "value": "5.2"}])
    assert "unapproved_override" in _codes(s, manifest=wrong_env)
    # a rollback to a version with no prompt bundle is rejected even when approved
    s9 = _with(_snapshot("beta"), svc={"STORY_EDIT_PLAN_VERSION": "9.9"}, wrk={"STORY_EDIT_PLAN_VERSION": "9.9"})
    ok9 = dict(MANIFEST, approved_overrides=[{"setting": "STORY_EDIT_PLAN_VERSION", "env": "beta", "value": "9.9"}])
    assert "prompt_missing" in _codes(s9, manifest=ok9)


def test_planner_default_drift_from_manifest_is_rejected(tmp_repo):
    p = tmp_repo / "packages/edit_planner/__init__.py"
    p.write_text(p.read_text().replace('_EDIT_PLAN_DEFAULT = "5.3"', '_EDIT_PLAN_DEFAULT = "5"'))
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


def test_ios_xcconfig_mixing_and_unbaked_apple_signin_are_rejected(tmp_repo):
    cfg = tmp_repo / "apps/ios/Story/Config"
    beta = (cfg / "Beta.xcconfig").read_text()
    dev = (cfg / "Development.xcconfig").read_text()
    (cfg / "Beta.xcconfig").write_text(re.sub(r"STORY_ENV_USER_POOL_ID = .*", "STORY_ENV_USER_POOL_ID = "
                                              + XC["Development"]["STORY_ENV_USER_POOL_ID"], beta))
    v, _ = gate.check_ios(tmp_repo)
    assert any(x.code == "ios_identity" and "share STORY_ENV_USER_POOL_ID" in x.message for x in v)
    (cfg / "Beta.xcconfig").write_text(beta)
    (cfg / "Development.xcconfig").write_text(dev.replace("STORY_APPLE_SIGNIN_AVAILABLE = 0", ""))
    v, _ = gate.check_ios(tmp_repo)
    assert any(x.code == "ios_apple_signin" for x in v)


def test_apple_signin_is_baked_and_not_read_from_launch_config():
    sw = (REPO / "apps/ios/Story/Story/Data/Auth/StoryAuthConfig.swift").read_text()
    assert "StoryLaunchConfig" not in sw.split("appleSignInAvailable")[1].split("static var domainHost")[0]
    assert "StoryAppleSignInAvailable" in (REPO / "apps/ios/Story/Story/Info.plist").read_text()


# --------------------------------------------------------------------------- post-deploy (live) verification
def _live(env="beta", *, sha="abc123def456", digest="sha256:" + "a" * 64, status="RUNNING", worker_sha=None,
          tags=None, files=None, snapshot=None, apple=None):
    return gate.LiveInfo(
        snapshot or _snapshot(env), status, f"123.dkr.ecr.us-east-1.amazonaws.com/story-{env}-api@{digest}",
        tags if tags is not None else [f"git-{sha}"], worker_sha if worker_sha is not None else sha,
        files if files is not None else {"BUILD_SHA", "prompts/edit_plan/5.3/system.md"}, apple)


def _live_codes(info, sha="abc123def456", digest="sha256:" + "a" * 64, manifest=MANIFEST):
    v, _ = gate.check_live(info, manifest, sha, digest)
    return {x.code for x in v}


def test_live_matching_deployment_is_accepted():
    assert _live_codes(_live()) == set()


def test_N10_incorrect_worker_build_sha_is_rejected():
    assert "worker_build_sha_mismatch" in _live_codes(_live(worker_sha="deadbeef0000"))
    assert "worker_build_sha_mismatch" in _live_codes(_live(worker_sha="abc123def456-dirty"))
    no_sha = gate.LiveInfo(_snapshot("beta"), "RUNNING", "r@sha256:" + "a" * 64, ["git-abc123def456"], None,
                           {"prompts/edit_plan/5.3/system.md"})
    assert "worker_build_sha_missing" in _live_codes(no_sha)


def test_live_api_image_must_match_expected_digest_and_build_sha_tag():
    assert "digest_mismatch" in _live_codes(_live(digest="sha256:" + "b" * 64), digest="sha256:" + "a" * 64)
    assert "api_build_sha_mismatch" in _live_codes(_live(tags=["git-111111111111"]))
    assert "service_not_running" in _live_codes(_live(status="OPERATION_IN_PROGRESS"))


def test_live_worker_zip_must_bundle_the_effective_planner_prompt():
    assert "worker_prompt_missing" in _live_codes(_live(files={"BUILD_SHA"}))


def test_live_runtime_environment_is_judged_by_the_same_rules_as_the_template():
    bad = _with(_snapshot("beta"), svc={"STORY_REQUIRE_AUTH": "0", "STORY_GUIDE_V2": "1"})
    codes = _live_codes(_live(snapshot=bad))
    assert {"auth_policy", "removed_setting"} <= codes


def test_live_apple_signin_advertised_without_idp_is_rejected():
    assert "ios_apple_signin" in _live_codes(_live(apple=False))
    assert "ios_apple_signin" not in _live_codes(_live(apple=True))


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
        z.writestr("prompts/edit_plan/5.3/system.md", "x")
    calls = []

    def aws(args):
        calls.append(args[:2])
        if args[:2] == ["apprunner", "list-services"]:
            return {"ServiceSummaryList": [{"ServiceName": "story-beta-api", "ServiceArn": "arn:x"}]}
        if args[:2] == ["apprunner", "describe-service"]:
            return {"Service": {"Status": "RUNNING", "SourceConfiguration": {"ImageRepository": {
                "ImageIdentifier": "r/story-beta-api@sha256:" + "a" * 64,
                "ImageConfiguration": {"RuntimeEnvironmentVariables": {"STORY_ENVIRONMENT": "beta"}}}}}}
        if args[:2] == ["lambda", "get-function"]:
            return {"Configuration": {"Environment": {"Variables": {"STORY_ENVIRONMENT": "beta"}}},
                    "Code": {"Location": "https://s3/presigned"}}
        if args[:2] == ["ecr", "describe-images"]:
            return {"imageDetails": [{"imageTags": ["git-abc123def456"]}]}
        raise AssertionError(args)

    info = gate.collect_live("beta", aws, fetch=lambda url: buf.getvalue())
    assert info.worker_build_sha == "abc123def456" and "prompts/edit_plan/5.3/system.md" in info.worker_files
    assert info.image_tags == ["git-abc123def456"] and info.service_status == "RUNNING"
    assert all(c[0] in ("apprunner", "lambda", "ecr") for c in calls)      # read-only service families only


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
        assert text.index("release_config_gate.py pre") < text.index("cdk deploy") < text.index("release_config_gate.py post"), wf
    ci = (REPO / ".github/workflows/ci.yml").read_text()
    assert "release_config_gate.py pre" in ci
