#!/usr/bin/env python3
"""release_config_gate.py -- mandatory pre-deploy and post-deploy release configuration gate (P1-G0).

ONE reusable mechanism for development, beta, gamma and production. Standard library only (CI runs it
before any dependency install). Reads the minimal release intent in release/release.json and compares it with
the configuration that is (pre) about to be deployed or (post) actually running. It never calls an AI model and
never prints a secret value.

  pre   python3 scripts/release_config_gate.py pre  --environment beta --template <cdk.out/story-beta-api.template.json>
                                                   [--worker-asset infrastructure/cdk/.worker-asset]
  post  python3 scripts/release_config_gate.py post --environment beta --expected-sha <12-char git sha>
                                                   [--expected-digest sha256:...] [--profile P] [--region R]

Exit code 0 = accepted. Non-zero = rejected; every violation is printed as `FAIL [code] message`.
An UNVERIFIABLE check (e.g. AWS access denied) is a FAILURE, never a pass: a gate that cannot look must not
bless a release.

Design rules
  * Accepted product features are CODE. They are not settings, so this gate has no per-feature "ON" list; it
    instead REJECTS any attempt to (re)introduce a removed switch (REMOVED_SETTINGS) or an unknown one.
  * Infrastructure identity is not duplicated into release.json: the Cognito/API identity pair is cross-checked
    against the iOS xcconfig that ships to the matching environment.
  * Emergency exceptions (planner rollback, degraded evidence persistence) must be listed in release.json
    (`approved_overrides` / `approved_degradations`) or the deploy is rejected.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO / "release" / "release.json"

# --------------------------------------------------------------------------------------------------------
# Registry of release-managed settings. Everything not listed here is rejected as unknown.
# (B = infrastructure identity, C = operational/security, D = AI routing, I = integration, K = kill-switch)
# --------------------------------------------------------------------------------------------------------
SERVICE_REQUIRED: dict[str, str] = {
    "STORY_ENVIRONMENT": "B",
    "STORY_JOBS_TABLE": "B", "STORY_JOBS_QUEUE_URL": "B", "STORY_STAGING_BUCKET": "B",
    "STORY_MEDIA_TABLE": "B", "STORY_MEDIA_BUCKET": "B", "STORY_STORIES_TABLE": "B",
    "STORY_UNDERSTANDING_TABLE": "B", "STORY_RATE_LIMIT_TABLE": "B", "STORY_USER_USAGE_TABLE": "B",
    "STORY_IDENTITY_CLAIMS_TABLE": "B", "STORY_USERS_TABLE": "B",
    "STORY_COGNITO_USER_POOL_ID": "B", "STORY_COGNITO_APP_CLIENT_ID": "B",
    "STORY_REQUIRE_AUTH": "C", "STORY_QUOTA_MODE": "C", "STORY_THROTTLE_MODE": "C",
    "STORY_QUOTA_USER_MONTHLY_USD": "C", "STORY_QUOTA_USER_DAILY_GENS": "C",
    "STORY_QUOTA_MAX_ACTIVE_JOBS": "C", "STORY_QUOTA_GLOBAL_MONTHLY_USD": "C",
    "STORY_OPENAI_MODEL": "D", "STORY_GEMINI_MODEL": "D",
    "STORY_MUSIC_PROVIDER": "I", "STORY_EPIDEMIC_MODE": "I", "STORY_REFERENCE_MEDIA_MODE": "I",
    "STORY_EVIDENCE_PERSIST_ENABLED": "K",
}
WORKER_REQUIRED: dict[str, str] = {
    "STORY_ENVIRONMENT": "B", "STORY_JOBS_TABLE": "B", "STORY_JOBS_QUEUE_URL": "B",
    "STORY_STAGING_BUCKET": "B", "STORY_USER_USAGE_TABLE": "B",
    "STORY_WORKER_DEADLINE_S": "C", "STORY_QUOTA_MODE": "C",
    "STORY_OPENAI_MODEL": "D", "STORY_GEMINI_MODEL": "D",
}
WORKER_NON_STORY_ALLOWED = {"PYTHONPATH"}
# Present ONLY as an approved emergency rollback (release.json approved_overrides); never in normal deploys.
OVERRIDE_ONLY = {"STORY_EDIT_PLAN_VERSION"}

# Settings that used to exist and were deliberately removed in P1-G0 (accepted features are code now, or the
# setting was dead/unsafe). Re-introducing any of them is a hard rejection with a specific message.
REMOVED_SETTINGS = {
    "STORY_GUIDE_V2", "STORY_SCENE_IMAGES", "STORY_JOBS_API_ENABLED", "STORY_LLM_FALLBACK_MODEL",
    "STORY_MODEL_PROVIDER", "STORY_REUSABLE_EVIDENCE", "STORY_EDITORIAL_TYPE_V2",
    "STORY_MULTIMODAL_PLANNING", "STORY_EDITPLAN_OBJECTIVE_DIRECTIVES", "STORY_EDITPLAN_BEST_VALID_RETENTION",
    "STORY_EDITPLAN_APPROX_DURATION_SOFT", "STORY_EDITPLAN_USEFUL_RANGE_SOFT",
    "STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE", "STORY_CRITIQUE_EXPLORE", "STORY_CREATIVE_REFINEMENT",
    "STORY_DIAG_BEACONS",
    "STORY_AU_MODEL", "STORY_COVERAGE_MODEL", "STORY_DIRECTOR_MODEL", "STORY_GUIDE_MODEL",
    "STORY_SCENE_MODEL", "STORY_EDIT_PLANNER_MODEL", "STORY_MUSIC_PLAN_MODEL", "STORY_DURATION_PLANNER_MODEL",
    "STORY_BEDROCK_MODEL", "STORY_BEDROCK_ROUTED_MODEL",
    "STORY_EDIT_PLANNER_REPAIR_ATTEMPTS", "STORY_EDIT_PLANNER_MAX_TOKENS", "STORY_EDIT_PLANNER_MAX_TOKENS_CEILING",
}
RESTRICTED_VALUE_MARKERS = ("anthropic", "claude", "bedrock")

# Product-feature switches that must not be re-introduced into the iOS Run scheme / baked config.
IOS_FORBIDDEN_SCHEME_KEYS = {
    "STORY_GUIDE_V2", "STORY_SCENE_IMAGES", "STORY_EDITORIAL_TYPE_V2", "STORY_MULTIMODAL_PLANNING",
    "STORY_REUSABLE_EVIDENCE", "STORY_CREATIVE_REFINEMENT", "STORY_CRITIQUE_EXPLORE", "STORY_DIAG_BEACONS",
}
# Backend-identity keys: baked from xcconfig per build configuration, never set by hand in the scheme.
IOS_IDENTITY_SCHEME_KEYS = {
    "STORY_API_BASE_URL", "STORY_COGNITO_REGION", "STORY_COGNITO_USER_POOL_ID",
    "STORY_COGNITO_APP_CLIENT_ID", "STORY_COGNITO_DOMAIN_PREFIX", "STORY_COGNITO_REDIRECT_URI",
    "STORY_BUILD_ENV",
}


@dataclass(frozen=True)
class Violation:
    code: str
    message: str

    def __str__(self) -> str:
        return f"FAIL [{self.code}] {self.message}"


@dataclass
class Snapshot:
    """Effective (or about-to-be-deployed) configuration of one environment.

    service: ordered (name, value) pairs as the App Runner service lists them (duplicates are detectable).
    worker:  Lambda environment map. A value of None means "unresolved CloudFormation intrinsic" (a Ref/GetAtt
    that only resolves at deploy time); those are presence-checked, not value-checked."""
    environment: str
    service: list[tuple[str, str | None]]
    worker: dict[str, str | None]
    source: str = "template"


# --------------------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text())


def parse_xcconfig(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def code_default_planner_version(repo: Path = REPO) -> str | None:
    src = (repo / "packages" / "edit_planner" / "__init__.py").read_text()
    m = re.search(r'^_EDIT_PLAN_DEFAULT\s*=\s*"([0-9]+(?:\.[0-9]+)*)"', src, re.M)
    return m.group(1) if m else None


def _lit(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def snapshot_from_template(template: dict, environment: str) -> Snapshot:
    res = template.get("Resources", {})
    svc = [r for r in res.values() if r.get("Type") == "AWS::AppRunner::Service"]
    wrk = [r for r in res.values() if r.get("Type") == "AWS::Lambda::Function"
           and "edit-plan-worker" in json.dumps(r.get("Properties", {}).get("FunctionName", ""))]
    if len(svc) != 1 or len(wrk) != 1:
        raise ValueError(f"template must contain exactly one App Runner service and one edit-plan worker "
                         f"(found {len(svc)} / {len(wrk)})")
    envs = (svc[0]["Properties"]["SourceConfiguration"]["ImageRepository"]
            ["ImageConfiguration"].get("RuntimeEnvironmentVariables", []))
    service = [(e["Name"], _lit(e.get("Value"))) for e in envs]
    wvars = wrk[0]["Properties"].get("Environment", {}).get("Variables", {})
    worker = {k: _lit(v) for k, v in wvars.items()}
    return Snapshot(environment, service, worker, "template")


# --------------------------------------------------------------------------------------------------------
# the rule engine (pure: used by pre, post, and the negative tests)
# --------------------------------------------------------------------------------------------------------
def check_snapshot(snap: Snapshot, manifest: dict, repo: Path = REPO) -> tuple[list[Violation], list[str]]:
    v: list[Violation] = []
    warn: list[str] = []
    env = snap.environment
    pol = manifest.get("environments", {}).get(env)
    if pol is None:
        return [Violation("unknown_environment", f"'{env}' is not defined in release/release.json")], warn

    names = [n for n, _ in snap.service]
    svc: dict[str, str | None] = dict(snap.service)
    wrk = snap.worker

    # --- duplicate active definitions ------------------------------------------------------------------
    for n in sorted({n for n in names if names.count(n) > 1}):
        v.append(Violation("duplicate_setting", f"service defines {n} {names.count(n)} times"))

    # --- removed / unknown / unapproved settings, mocks, restricted providers ---------------------------
    approved = {(o.get("setting"), o.get("env"), str(o.get("value"))) for o in manifest.get("approved_overrides", [])}
    for scope, keys, allowed in (("service", set(svc), set(SERVICE_REQUIRED)),
                                 ("worker", set(wrk), set(WORKER_REQUIRED) | WORKER_NON_STORY_ALLOWED)):
        for n in sorted(keys):
            if n in allowed:
                continue
            if n in OVERRIDE_ONLY:
                continue  # judged below
            if n in REMOVED_SETTINGS:
                v.append(Violation("removed_setting",
                                   f"{scope} sets {n}, which was removed in P1-G0 (accepted behavior is code)"))
            else:
                v.append(Violation("unknown_setting", f"{scope} sets unmanaged setting {n} (unapproved override)"))
    for scope, mapping in (("service", svc), ("worker", wrk)):
        for n, val in mapping.items():
            if "MOCK" in n.upper():
                v.append(Violation("mock_in_release", f"{scope} enables mock/test setting {n}"))
            if val and any(m in val.lower() for m in RESTRICTED_VALUE_MARKERS):
                v.append(Violation("restricted_provider",
                                   f"{scope} {n} references a restricted Anthropic/Bedrock identifier"))

    # --- required settings -------------------------------------------------------------------------------
    for n in SERVICE_REQUIRED:
        if n not in svc:
            v.append(Violation("missing_required", f"service is missing required setting {n}"))
    for n in WORKER_REQUIRED:
        if n not in wrk:
            v.append(Violation("missing_required", f"worker is missing required setting {n}"))

    # --- required capabilities (integration settings the release depends on) ----------------------------
    for n, want in manifest.get("required_everywhere", {}).items():
        have = svc.get(n)
        if n not in svc:
            v.append(Violation("capability_missing", f"required release capability {n}={want} is absent in {env}"))
        elif have is not None and have != want:
            v.append(Violation("capability_missing", f"{n}={have} but the release requires {want}"))

    # --- API / worker agreement --------------------------------------------------------------------------
    for n in ("STORY_ENVIRONMENT", "STORY_OPENAI_MODEL", "STORY_GEMINI_MODEL", "STORY_QUOTA_MODE"):
        if n in svc and n in wrk and svc[n] is not None and wrk[n] is not None and svc[n] != wrk[n]:
            v.append(Violation("api_worker_mismatch", f"{n}: service={svc[n]} worker={wrk[n]}"))

    # --- planner: code default, rollback override, prompt assets ----------------------------------------
    want_ver = manifest.get("planner", {}).get("version")
    code_ver = code_default_planner_version(repo)
    if code_ver != want_ver:
        v.append(Violation("planner_default_mismatch",
                           f"code default planner is {code_ver!r} but release/release.json requires {want_ver!r}"))
    s_ov, w_ov = svc.get("STORY_EDIT_PLAN_VERSION"), wrk.get("STORY_EDIT_PLAN_VERSION")
    if ("STORY_EDIT_PLAN_VERSION" in svc) != ("STORY_EDIT_PLAN_VERSION" in wrk) or (s_ov != w_ov):
        v.append(Violation("planner_mismatch",
                           f"EditPlan version differs between API ({s_ov or 'code default'}) and "
                           f"worker ({w_ov or 'code default'})"))
    effective = s_ov or w_ov or code_ver
    for scope, val in (("service", s_ov), ("worker", w_ov)):
        if val is not None and ("STORY_EDIT_PLAN_VERSION", env, str(val)) not in approved:
            v.append(Violation("unapproved_override",
                               f"{scope} pins STORY_EDIT_PLAN_VERSION={val} without an approved_overrides entry "
                               f"for {env}"))
    if effective and not (repo / "prompts" / "edit_plan" / effective / "system.md").is_file():
        v.append(Violation("prompt_missing", f"prompts/edit_plan/{effective}/system.md does not exist"))

    # --- security / operational policy -------------------------------------------------------------------
    for key, setting in (("require_auth", "STORY_REQUIRE_AUTH"), ("quota_mode", "STORY_QUOTA_MODE"),
                         ("throttle_mode", "STORY_THROTTLE_MODE"), ("user_monthly_usd", "STORY_QUOTA_USER_MONTHLY_USD")):
        want = pol.get(key)
        have = svc.get(setting)
        if want is not None and setting in svc and have is not None and have != want:
            code = {"require_auth": "auth_policy", "quota_mode": "quota_policy",
                    "throttle_mode": "throttle_policy", "user_monthly_usd": "quota_policy"}[key]
            v.append(Violation(code, f"{env}: {setting}={have} but release requires {want}"))
    wq = wrk.get("STORY_QUOTA_MODE")
    if wq is not None and pol.get("quota_mode") and wq != pol["quota_mode"]:
        v.append(Violation("quota_policy", f"{env}: worker STORY_QUOTA_MODE={wq} but release requires {pol['quota_mode']}"))

    # --- evidence persistence (operational privacy kill-switch) -----------------------------------------
    ep_want = pol.get("evidence_persist")
    ep_have = svc.get("STORY_EVIDENCE_PERSIST_ENABLED")
    if ep_want is not None and ep_have is not None and ep_have != ep_want:
        degraded_ok = any(d.get("env") == env and d.get("capability") == "evidence_persist"
                          for d in manifest.get("approved_degradations", []))
        if degraded_ok:
            warn.append(f"{env}: evidence persistence is {ep_have} (APPROVED DEGRADED state; reuse falls back to "
                        f"full re-analysis)")
        else:
            v.append(Violation("evidence_persist_off",
                               f"{env}: STORY_EVIDENCE_PERSIST_ENABLED={ep_have} but the release requires {ep_want}; "
                               f"promotion needs an approved_degradations entry"))

    # --- environment identity ----------------------------------------------------------------------------
    for scope, mapping in (("service", svc), ("worker", wrk)):
        if mapping.get("STORY_ENVIRONMENT") not in (None, env):
            v.append(Violation("identity_mixed",
                               f"{scope} STORY_ENVIRONMENT={mapping['STORY_ENVIRONMENT']} in a {env} deployment"))
        for n, val in mapping.items():
            for other in re.findall(r"story-(development|beta|gamma|production)-", val or ""):
                if other != env:
                    v.append(Violation("identity_mixed", f"{scope} {n} references a {other} resource in {env}"))
    xc = pol.get("xcconfig")
    if xc:
        cfg = _xcconfig_for(repo, xc)
        if cfg is not None:
            for key, setting in (("STORY_ENV_USER_POOL_ID", "STORY_COGNITO_USER_POOL_ID"),
                                 ("STORY_ENV_APP_CLIENT_ID", "STORY_COGNITO_APP_CLIENT_ID")):
                have = svc.get(setting)
                if have is not None and have != cfg.get(key):
                    other = _which_env_owns(repo, key, have)
                    v.append(Violation("identity_mixed",
                                       f"{env} API {setting} does not match the {xc} iOS build"
                                       + (f" (it is the {other} value)" if other else "")))
    return v, warn


def _xcconfig_for(repo: Path, name: str) -> dict[str, str] | None:
    p = repo / "apps" / "ios" / "Story" / "Config" / f"{name}.xcconfig"
    return parse_xcconfig(p) if p.is_file() else None


def _which_env_owns(repo: Path, key: str, value: str) -> str | None:
    for name in ("Development", "Beta"):
        cfg = _xcconfig_for(repo, name)
        if cfg and cfg.get(key) == value:
            return name.lower()
    return None


# --------------------------------------------------------------------------------------------------------
# iOS build-configuration gate (independent of Xcode Run arguments)
# --------------------------------------------------------------------------------------------------------
def check_ios(repo: Path = REPO, scheme: Path | None = None) -> tuple[list[Violation], list[str]]:
    v: list[Violation] = []
    warn: list[str] = []
    dev, beta = _xcconfig_for(repo, "Development"), _xcconfig_for(repo, "Beta")
    if dev is None or beta is None:
        return [Violation("ios_config_missing", "Development.xcconfig / Beta.xcconfig not found")], warn
    for name, cfg, want in (("Development", dev, "development"), ("Beta", beta, "beta")):
        if cfg.get("STORY_BUILD_ENV") != want:
            v.append(Violation("ios_identity", f"{name}.xcconfig STORY_BUILD_ENV={cfg.get('STORY_BUILD_ENV')} (expected {want})"))
        for k in ("STORY_ENV_API_BASE_URL", "STORY_ENV_USER_POOL_ID", "STORY_ENV_APP_CLIENT_ID", "STORY_ENV_DOMAIN_PREFIX"):
            if not cfg.get(k):
                v.append(Violation("ios_identity", f"{name}.xcconfig is missing {k}"))
        if want not in (cfg.get("STORY_ENV_DOMAIN_PREFIX") or ""):
            v.append(Violation("ios_identity", f"{name}.xcconfig Cognito domain prefix does not name {want}"))
    for k in ("STORY_ENV_API_BASE_URL", "STORY_ENV_USER_POOL_ID", "STORY_ENV_APP_CLIENT_ID"):
        if dev.get(k) and dev.get(k) == beta.get(k):
            v.append(Violation("ios_identity", f"Development and Beta xcconfig share {k} (environments mixed)"))
    # Apple Sign In must be an explicit, baked, per-environment value (never an Xcode Run argument).
    for name, cfg in (("Development", dev), ("Beta", beta)):
        if cfg.get("STORY_APPLE_SIGNIN_AVAILABLE") not in ("0", "1"):
            v.append(Violation("ios_apple_signin",
                               f"{name}.xcconfig must bake STORY_APPLE_SIGNIN_AVAILABLE as 0 or 1 explicitly"))
        elif cfg["STORY_APPLE_SIGNIN_AVAILABLE"] == "1":
            warn.append(f"{name}: Apple Sign In is advertised; post-deploy gate requires the SignInWithApple IdP on its pool")
    # Shared schemes: no product-feature switches, no hand-set backend identity, no duplicate enabled keys.
    # (Identity comes from the xcconfig selected by the scheme's build configuration; Debug may still be
    # re-pointed from a LOCAL, uncommitted scheme, but a tracked scheme must not carry it.)
    if scheme is not None:
        scheme_files = [scheme]
    else:
        sdir = repo / "apps" / "ios" / "Story" / "Story.xcodeproj" / "xcshareddata" / "xcschemes"
        scheme_files = sorted(sdir.glob("*.xcscheme")) if sdir.is_dir() else []
    for sp in scheme_files:
        enabled: list[str] = []
        for ev in ET.parse(sp).getroot().iter("EnvironmentVariable"):
            if ev.get("isEnabled") == "YES" and ev.get("key"):
                enabled.append(ev.get("key"))
        for k in sorted(set(enabled)):
            if enabled.count(k) > 1:
                v.append(Violation("duplicate_setting", f"{sp.name} enables {k} {enabled.count(k)} times"))
            if k in IOS_FORBIDDEN_SCHEME_KEYS:
                v.append(Violation("ios_scheme_override", f"{sp.name} enables removed feature switch {k}"))
            if k in IOS_IDENTITY_SCHEME_KEYS:
                v.append(Violation("ios_scheme_override",
                                   f"{sp.name} hand-sets backend identity {k}; identity comes from the xcconfig"))
    return v, warn


# --------------------------------------------------------------------------------------------------------
# worker asset (pre-deploy)
# --------------------------------------------------------------------------------------------------------
def check_worker_asset(asset: Path, snap: Snapshot, manifest: dict, repo: Path = REPO,
                       require_clean: bool = False) -> list[Violation]:
    v: list[Violation] = []
    bs = asset / "BUILD_SHA"
    if not bs.is_file():
        v.append(Violation("worker_build_sha_missing", "worker asset has no BUILD_SHA file"))
    elif require_clean and (bs.read_text().strip().endswith("-dirty") or bs.read_text().strip() in ("", "unknown")):
        v.append(Violation("worker_build_sha_dirty",
                           f"worker asset BUILD_SHA is '{bs.read_text().strip()}': a release must be built from a clean, "
                           f"identifiable commit"))
    effective = (dict(snap.service).get("STORY_EDIT_PLAN_VERSION") or snap.worker.get("STORY_EDIT_PLAN_VERSION")
                 or manifest.get("planner", {}).get("version"))
    if not (asset / "prompts" / "edit_plan" / str(effective) / "system.md").is_file():
        v.append(Violation("prompt_missing", f"worker asset lacks prompts/edit_plan/{effective}/system.md"))
    return v


# --------------------------------------------------------------------------------------------------------
# post-deploy: effective runtime state from AWS (read-only)
# --------------------------------------------------------------------------------------------------------
class AwsUnavailable(Exception):
    """AWS could not be read (access denied, SSO expired, not found). The gate treats this as FAILURE."""


AwsRunner = Callable[[list[str]], Any]


def default_aws(profile: str | None, region: str) -> AwsRunner:
    def run(args: list[str]) -> Any:
        cmd = ["aws", *args, "--region", region, "--output", "json"]
        if profile:
            cmd += ["--profile", profile]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise AwsUnavailable(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "aws failed")
        return json.loads(p.stdout or "null")
    return run


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:  # presigned Lambda code URL
        return r.read()


@dataclass
class LiveInfo:
    snapshot: Snapshot
    service_status: str
    image_identifier: str
    image_tags: list[str]
    worker_build_sha: str | None
    worker_files: set[str]
    apple_idp_present: bool | None = None
    notes: list[str] = field(default_factory=list)


def collect_live(environment: str, aws: AwsRunner, fetch: Callable[[str], bytes] = fetch_bytes,
                 want_apple_check: bool = False, user_pool_id: str | None = None) -> LiveInfo:
    name = f"story-{environment}-api"
    services = aws(["apprunner", "list-services"])["ServiceSummaryList"]
    arn = next((s["ServiceArn"] for s in services if s["ServiceName"] == name), None)
    if not arn:
        raise AwsUnavailable(f"App Runner service {name} not found")
    svc = aws(["apprunner", "describe-service", "--service-arn", arn])["Service"]
    img = svc["SourceConfiguration"]["ImageRepository"]
    envmap = img["ImageConfiguration"].get("RuntimeEnvironmentVariables") or {}
    service = [(k, v) for k, v in envmap.items()]
    fn = aws(["lambda", "get-function", "--function-name", f"story-{environment}-edit-plan-worker"])
    wvars = fn["Configuration"].get("Environment", {}).get("Variables", {}) or {}
    ident = img["ImageIdentifier"]
    digest = ident.split("@", 1)[1] if "@" in ident else None
    tags: list[str] = []
    if digest:
        d = aws(["ecr", "describe-images", "--repository-name", name, "--image-ids", f"imageDigest={digest}"])
        tags = list((d.get("imageDetails") or [{}])[0].get("imageTags") or [])
    zdata = fetch(fn["Code"]["Location"])
    zf = zipfile.ZipFile(io.BytesIO(zdata))
    files = set(zf.namelist())
    wsha = zf.read("BUILD_SHA").decode().strip() if "BUILD_SHA" in files else None
    apple = None
    if want_apple_check and user_pool_id:
        provs = aws(["cognito-idp", "list-identity-providers", "--user-pool-id", user_pool_id])["Providers"]
        apple = any(p.get("ProviderName") == "SignInWithApple" for p in provs)
    return LiveInfo(Snapshot(environment, service, dict(wvars), "live"), svc.get("Status", "?"), ident, tags,
                    wsha, files, apple)


def check_live(info: LiveInfo, manifest: dict, expected_sha: str, expected_digest: str | None,
               repo: Path = REPO) -> tuple[list[Violation], list[str]]:
    v, warn = check_snapshot(info.snapshot, manifest, repo)
    env = info.snapshot.environment
    if info.service_status != "RUNNING":
        v.append(Violation("service_not_running", f"{env} API service status is {info.service_status}"))
    digest = info.image_identifier.split("@", 1)[1] if "@" in info.image_identifier else None
    if digest is None:
        v.append(Violation("digest_not_pinned", "API service is not pinned to an immutable image digest"))
    elif expected_digest and digest != expected_digest:
        v.append(Violation("digest_mismatch", f"running API digest {digest} != expected {expected_digest}"))
    if f"git-{expected_sha}" not in info.image_tags:
        v.append(Violation("api_build_sha_mismatch",
                           f"running API image is not tagged git-{expected_sha} (tags: {', '.join(info.image_tags) or 'none'})"))
    ws = info.worker_build_sha
    if ws is None:
        v.append(Violation("worker_build_sha_missing", "deployed worker zip has no BUILD_SHA"))
    elif ws != expected_sha:
        v.append(Violation("worker_build_sha_mismatch",
                           f"deployed worker BUILD_SHA {ws} != expected {expected_sha}"
                           + (" (built from a dirty tree)" if ws.endswith("-dirty") else "")))
    eff = (dict(info.snapshot.service).get("STORY_EDIT_PLAN_VERSION")
           or info.snapshot.worker.get("STORY_EDIT_PLAN_VERSION")
           or manifest.get("planner", {}).get("version"))
    if f"prompts/edit_plan/{eff}/system.md" not in info.worker_files:
        v.append(Violation("worker_prompt_missing", f"deployed worker zip lacks prompts/edit_plan/{eff}/system.md"))
    if info.apple_idp_present is False:
        v.append(Violation("ios_apple_signin", "an iOS build advertises Apple Sign In but the Cognito pool has no SignInWithApple IdP"))
    return v, warn


# --------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------
def _report(v: list[Violation], warn: list[str], label: str) -> int:
    for w in warn:
        print(f"WARN {w}")
    if v:
        for x in v:
            print(x)
        print(f"RELEASE CONFIG GATE ({label}): REJECTED - {len(v)} violation(s)")
        return 1
    print(f"RELEASE CONFIG GATE ({label}): ACCEPTED")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    pre = sub.add_parser("pre")
    pre.add_argument("--environment", required=True)
    pre.add_argument("--template", required=True, type=Path)
    pre.add_argument("--worker-asset", type=Path)
    pre.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    pre.add_argument("--require-clean-asset", action="store_true",
                     help="reject a worker asset whose BUILD_SHA is dirty/unknown (deploy workflows and CI)")
    pre.add_argument("--scheme", type=Path, help="audit only this scheme file (default: every tracked shared scheme)")
    post = sub.add_parser("post")
    post.add_argument("--environment", required=True)
    post.add_argument("--expected-sha", required=True)
    post.add_argument("--expected-digest")
    post.add_argument("--profile")
    post.add_argument("--region", default="us-east-1")
    post.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    post.add_argument("--wait-seconds", type=int, default=600,
                      help="how long to wait for the API service to leave OPERATION_IN_PROGRESS (default 600)")
    a = ap.parse_args(argv)
    manifest = load_manifest(a.manifest)

    if a.mode == "pre":
        snap = snapshot_from_template(json.loads(a.template.read_text()), a.environment)
        v, warn = check_snapshot(snap, manifest)
        iv, iw = check_ios(REPO, a.scheme)
        v, warn = v + iv, warn + iw
        if a.worker_asset:
            v += check_worker_asset(a.worker_asset, snap, manifest, require_clean=a.require_clean_asset)
        return _report(v, warn, f"pre-deploy {a.environment}")

    aws = default_aws(a.profile, a.region)
    xc = manifest["environments"].get(a.environment, {}).get("xcconfig")
    cfg = _xcconfig_for(REPO, xc) if xc else None
    apple = bool(cfg and cfg.get("STORY_APPLE_SIGNIN_AVAILABLE") == "1")
    try:
        deadline = time.monotonic() + a.wait_seconds
        while True:
            info = collect_live(a.environment, aws, want_apple_check=apple,
                                user_pool_id=(cfg or {}).get("STORY_ENV_USER_POOL_ID"))
            if info.service_status != "OPERATION_IN_PROGRESS" or time.monotonic() >= deadline:
                break
            time.sleep(20)
    except AwsUnavailable as e:
        print(Violation("unverifiable", f"cannot read the running {a.environment} configuration: {e}"))
        print(f"RELEASE CONFIG GATE (post-deploy {a.environment}): REJECTED - unverifiable is a failure")
        return 2
    v, warn = check_live(info, manifest, a.expected_sha, a.expected_digest)
    return _report(v, warn, f"post-deploy {a.environment}")


if __name__ == "__main__":
    sys.exit(main())
