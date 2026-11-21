"""Billing V1 enforcement wiring (separate from the operational quota gate).

`STORY_BILLING_MODE` = off | observe | enforce (default off; anything else is treated as off).
  off      nothing is read or written: existing beta behaviour is unchanged.
  observe  decisions are computed against a SHADOW ledger (`billing-shadow#` items). Nothing customer-visible is debited,
           nothing is ever denied; would-deny outcomes are logged and counted.
  enforce  the LIVE ledger gates requests: HTTP 402 with a typed error, fail-closed 503 on a billing-store outage.

Two meters (they are independent of `quota_gate`, which keeps protecting spend, rate and concurrency):
  video   one credit per SUCCESSFUL video generation (Create, Another Version, Revise are all edit-plan jobs)
  moment  one allowance unit per UNIQUE newly analysed Moment (asset understanding)

Paid-route coverage: every route the throttle classifies as an expensive (paid) class MUST appear in exactly one of
BILLED_ROUTES or BILLING_EXEMPT below. A test enforces this, so a new paid endpoint cannot ship unclassified.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.throttle import ROUTE_CLASS

from billing.analysis import abandon as _abandon_analysis, complete as _complete_analysis, frames_fingerprint, normalize_claim, plan_analysis
from billing.apple import AppleError
from billing import (
    BillingConfigError, BillingDenied, BillingLedger, BillingStoreError, CONTRACT_VERSION, Hold, MODE_ENFORCE,
    MODE_OBSERVE, MODE_OFF, billing_mode, validate_billing_config,
)


def validate_startup() -> str:
    """Fail application startup on an invalid billing configuration (see packages/billing/config.py)."""
    return validate_billing_config()

log = logging.getLogger("story.billing")

# Routes that SPEND an entitlement unit.
BILLED_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/v1/edit-plan"): "video",          # sync planner (text-only)
    ("POST", "/v1/edit-plan-mm"): "video",       # sync planner (multimodal)
    ("POST", "/v1/edit-plan-jobs"): "video",     # async planner: the path the app uses for Create / Version / Revise
    ("POST", "/v1/asset-understanding"): "moment",
}

# Paid-class routes that deliberately do NOT spend an allowance: Story Guide, AI Ideas and the supporting AI calls stay
# available inside the existing fair-use throttle/quota. Listed explicitly so classification is a decision, not an accident.
BILLING_EXEMPT: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/v1/creative-intent"), ("POST", "/v1/interpret-revision"), ("POST", "/v1/scene-understanding"),
    ("POST", "/v1/story-coverage"), ("POST", "/v1/story-coverage/v2"), ("POST", "/v1/story-guide"),
    ("POST", "/v1/story-guide-v2"), ("POST", "/v1/story-guide-refine"), ("POST", "/v1/music-plan"),
    ("POST", "/v1/duration-recommendation"), ("POST", "/v1/director/initialize"), ("POST", "/v1/director/next"),
    ("POST", "/v1/music/candidates"), ("POST", "/v1/music/search"), ("POST", "/v1/music/analysis"),
    ("POST", "/v1/music/soundtrack"), ("POST", "/v1/scene-image"), ("POST", "/v1/scene-video"),
    ("POST", "/v1/story-coverage/v2/jobs"),   # coverage is analysis support, not a video output
})

_SYNC_VIDEO = frozenset(k for k, v in BILLED_ROUTES.items() if v == "video" and k[1] != "/v1/edit-plan-jobs")

REFUND_REASONS = frozenset({"render_failed", "export_failed", "playback_failed"})
_STORE_RETRY_AFTER = 30


# ---- ledger resolution -------------------------------------------------------------------------------------------

def _ledger(request: Request) -> Optional["BillingLedger"]:
    mode = billing_mode()
    if mode == MODE_OFF:
        return None
    ov = getattr(request.app.state, "_billing_ledger_override", None)
    if ov is not None:
        return ov.get(mode) if isinstance(ov, dict) else ov
    if not os.environ.get("STORY_USER_USAGE_TABLE", ""):
        return None      # unprovisioned environment: inert, like quota_gate
    cache = getattr(request.app.state, "_billing_ledgers", None)
    if cache is None:
        cache = request.app.state._billing_ledgers = {}
    if mode not in cache:
        cache[mode] = BillingLedger(shadow=(mode == MODE_OBSERVE))
    return cache[mode]


def _live_ledger(request: Request) -> Optional["BillingLedger"]:
    """The LIVE ledger, whatever STORY_BILLING_MODE is (Apple purchases are only ever written there). None when unprovisioned."""
    if billing_mode() == MODE_ENFORCE:
        led = _ledger(request)
        if led is not None:
            return led
    ov = getattr(request.app.state, "_apple_billing_override", None)
    if ov is not None:
        return ov.ledger
    ov = getattr(request.app.state, "_live_billing_ledger_override", None)
    if ov is not None:
        return ov
    if not os.environ.get("STORY_USER_USAGE_TABLE", ""):
        return None
    led = getattr(request.app.state, "_live_billing_ledger", None)
    if led is None:
        led = request.app.state._live_billing_ledger = BillingLedger(shadow=False)
    return led


def live_plus_active(request: Request, uid: str) -> bool:
    """Billing V2: does this account hold a VERIFIED, currently active (or grace) Apple subscription, read from the live ledger in
    EVERY billing mode? Used to exempt a paying subscriber from the per-user quota caps (user_monthly_usd, user_daily_gens) and to
    keep observe mode from logging would-deny for a paying customer (S2). Never raises; a read failure is retried once, then answers False, so the
    caller falls back to the NORMAL caps (never uncapped). Read-only: never creates an entitlement."""
    led = None
    for attempt in (1, 2):      # S5: one retry of the read before falling back
        try:
            led = _live_ledger(request)
            if led is None:
                return False
            ent = led.get_entitlement(uid)
            return bool(ent is not None and ent.has_active_subscription(led._now()))
        except Exception as e:  # noqa: BLE001
            log.warning("billing_live_plus_read_error",
                        extra={"error": f"{type(e).__name__}"[:80], "attempt": attempt,
                               "fallback": "normal_caps" if attempt == 2 else "retry"})
    return False


def principal_uid(request: Request) -> Optional[str]:
    p = getattr(request.state, "principal", None)
    if p is None or getattr(p, "is_legacy", False) or not getattr(p, "story_user_id", None):
        return None
    return p.story_user_id


def _metric(request: Request, name: str, kind: str) -> None:
    hook = getattr(request.app.state, "_quota_metric_hook", None)
    if hook is not None:
        try:
            hook(name, f"billing_{kind}")
        except Exception:  # noqa: BLE001
            pass


# ---- responses ---------------------------------------------------------------------------------------------------

def denial_response(d: "BillingDenied") -> JSONResponse:
    """HTTP 402 for an entitlement/payment restriction. 429 stays reserved for operational rate limiting."""
    return JSONResponse(status_code=402, content={
        "error": d.code, "action": d.action, "contract_version": CONTRACT_VERSION, "entitlement": d.snapshot})


def store_unavailable_response() -> JSONResponse:
    return JSONResponse(status_code=503, headers={"Retry-After": str(_STORE_RETRY_AFTER)},
                        content={"error": "billing_unavailable", "retry_after_seconds": _STORE_RETRY_AFTER})


# ---- gate objects ------------------------------------------------------------------------------------------------

@dataclass
class Gate:
    ledger: "BillingLedger"
    uid: str
    kind: str            # video | moment
    key: str             # scoped operation id (video) or moment id
    hold: "Hold"

    @property
    def owns_charge(self) -> bool:
        return bool(self.hold.charged)

    @property
    def owns_operation(self) -> bool:
        """Billing V2: this call created (or reclaimed) the operation RECORD. An unlimited (unmetered) hold owns its record
        without a charge, and must still release it when the operation fails."""
        return bool(self.hold.owns)


def _reserve(request: Request, kind: str, uid: str, key: str):
    """Returns (gate | None, response | None). `response` is set only in enforce mode and is the 402/503 to return."""
    led = _ledger(request)
    if led is None:
        return None, None
    enforce = billing_mode() == MODE_ENFORCE
    try:
        hold = led.reserve_video(uid, key)
    except BillingDenied as d:
        if enforce:
            _metric(request, "BillingDenied", kind)
            log.info("billing_denied", extra={"kind": kind, "code": d.code, "story_user_id": uid})
            return None, denial_response(d)
        if led.shadow and live_plus_active(request, uid):
            # S2: the shadow ledger models a paying subscriber as a Free starter. Not a would-deny: Plus is unlimited.
            _metric(request, "BillingObservePlus", kind)
            return None, None
        _metric(request, "BillingWouldDeny", kind)
        log.info("billing_would_deny", extra={"kind": kind, "code": d.code, "story_user_id": uid})
        return None, None
    except BillingStoreError as e:
        log.warning("billing_store_error", extra={"kind": kind, "error": str(e)[:160]})
        _metric(request, "BillingStoreError", kind)
        # Paid operation + billing outage: fail CLOSED when enforcing (we cannot account), ignore when observing.
        return None, (store_unavailable_response() if enforce else None)
    _metric(request, "BillingReserved", kind)
    return Gate(led, uid, kind, key, hold), None


def reserve_video(request: Request, uid: str, scoped_op_id: str):
    return _reserve(request, "video", uid, scoped_op_id)


def settle(gate: Optional[Gate]) -> None:
    """Spend the held video credit. Never raises into the response: an unsettled hold is reconciled by the job sweep, and an
    under-charge is preferred to a failed customer response."""
    if gate is None:
        return
    try:
        gate.ledger.settle_video(gate.uid, gate.key)
    except Exception as e:  # noqa: BLE001
        log.warning("billing_settle_error", extra={"kind": gate.kind, "error": str(e)[:160]})


def release(gate: Optional[Gate]) -> None:
    """Return a held video credit after a failed operation. Only the call that OWNS the charge releases it, so a duplicate
    request failing cannot refund a charge that another request is still earning."""
    if gate is None or not gate.owns_operation:
        return
    try:
        gate.ledger.release_video(gate.uid, gate.key)
    except Exception as e:  # noqa: BLE001
        log.warning("billing_release_error", extra={"kind": gate.kind, "error": str(e)[:160]})


# ---- sync video routes (middleware) ------------------------------------------------------------------------------

async def billing_middleware(request: Request, call_next):
    """Gates the SYNCHRONOUS planner routes (the async job route and AU are gated in their handlers, where the
    scoped operation id / moment id are known). Registered inside auth so request.state.principal exists."""
    key = (request.method, request.url.path)
    if key not in _SYNC_VIDEO or billing_mode() == MODE_OFF:
        return await call_next(request)
    uid = principal_uid(request)
    if uid is None:
        return await call_next(request)
    gate, resp = reserve_video(request, uid, f"sync:{uuid.uuid4()}")
    if resp is not None:
        return resp
    try:
        response = await call_next(request)
    except Exception:
        release(gate)
        raise
    if 200 <= response.status_code < 300:
        settle(gate)
    else:
        release(gate)
    return response


# ---- async video job submit --------------------------------------------------------------------------------------

def submit_reserve_video(request: Request, uid: str, scoped_op_id: str, *, created: bool):
    """Reserve one video credit for a NEWLY CREATED job. A recovered duplicate (same operation id, job row already
    exists) reserves nothing: the credit was taken at first submit, so a client retry never double-charges."""
    if not created:
        return None, None
    return reserve_video(request, uid, scoped_op_id)


# ---- asset analysis (Moment meter) ---------------------------------------------------------------------------------

def verify_source(request: Request, uid: str, claim_sha: Optional[str]) -> bool:
    """True only when THIS account owns a CLOUD-VERIFIED original whose full-file sha256 equals the client's claim. The media
    record id is uuid5(owner + sha256), so this is one GetItem keyed by the account: another account's media can never
    verify a claim, and an unverified, uploading or failed record never does either. Any error means "not verified"."""
    claim = normalize_claim(claim_sha)
    if not claim or not os.environ.get("STORY_MEDIA_TABLE") and getattr(request.app.state, "_media_store_override", None) is None:
        return False
    try:
        from media_store import MediaStore, STATE_CLOUD_VERIFIED, cloud_media_id_for
        store = getattr(request.app.state, "_media_store_override", None) or MediaStore()
        rec = store.get(uid, cloud_media_id_for(uid, claim))
        return bool(rec and rec.get("state") == STATE_CLOUD_VERIFIED and str(rec.get("content_sha256", "")).lower() == claim)
    except Exception:  # noqa: BLE001
        return False


@dataclass
class AnalysisOutcome:
    value: object = None        # AUResult when the model ran; None when a cached result was served
    reused: object = None       # the cached understanding when served from the ledger
    response: Optional[JSONResponse] = None


def _in_progress_response() -> JSONResponse:
    return JSONResponse(status_code=503, headers={"Retry-After": "5"},
                        content={"error": "analysis_in_progress", "retry_after_seconds": 5})


async def run_analysis(request: Request, uid: str, moment_id: str, *, frames, claim_sha, version, analyze, to_json, from_json):
    """Run one asset analysis through the source-binding ledger. Returns (value, reused, response); exactly one is meaningful.
    Exceptions from `analyze` propagate AFTER the allowance is returned (only the request that owns the charge returns it)."""
    led = _ledger(request)
    if led is None:
        return await analyze(), None, None
    enforce = billing_mode() == MODE_ENFORCE
    fp = frames_fingerprint(frames)
    from model_gateway import current_call_context
    corr = str(current_call_context().get("correlation_id") or uuid.uuid4())      # joins the ledger record to model_call_usage lines
    deadline = time.monotonic() + led.cfg.analysis_wait_s
    verified = await run_in_threadpool(verify_source, request, uid, claim_sha)   # blocking DynamoDB read: off the event loop
    plan = None
    while True:
        try:
            plan = await run_in_threadpool(lambda: plan_analysis(led, uid, moment_id, fp=fp, version=version, claim_sha=claim_sha,
                                                                 verified=verified, corr=corr))
        except BillingDenied as d:
            if enforce:
                _metric(request, "BillingDenied", "moment")
                log.info("billing_denied", extra={"kind": "moment", "code": d.code, "story_user_id": uid})
                return None, None, denial_response(d)
            if led.shadow and await run_in_threadpool(live_plus_active, request, uid):
                _metric(request, "BillingObservePlus", "moment")          # S2: a paying subscriber is never a would-deny
                return await analyze(), None, None
            _metric(request, "BillingWouldDeny", "moment")
            log.info("billing_would_deny", extra={"kind": "moment", "code": d.code, "story_user_id": uid})
            return await analyze(), None, None
        except BillingStoreError as e:
            log.warning("billing_store_error", extra={"kind": "moment", "error": str(e)[:160]})
            _metric(request, "BillingStoreError", "moment")
            if enforce:
                return None, None, store_unavailable_response()
            return await analyze(), None, None
        if plan.action == "reuse":
            try:
                cached = from_json(plan.result)
            except Exception:  # noqa: BLE001 - a cached result that no longer validates is a refresh, not an error
                cached = None
            if cached is not None:
                if enforce:
                    _metric(request, "BillingAnalysisReused", "moment")
                    log.info("billing_analysis_reused", extra={"story_user_id": uid, "moment_key": plan.key[:60], "reason": plan.reason})
                    return None, cached, None
                log.info("billing_would_reuse", extra={"story_user_id": uid, "moment_key": plan.key[:60]})
                return await analyze(), None, None
            if await run_in_threadpool(led.begin_refresh, uid, plan.key, corr):
                plan.action, plan.reason = "refresh", "cached_result_invalid"
            else:
                plan.action = "in_flight"
        if plan.action != "in_flight":
            break
        if not enforce:
            log.info("billing_would_coalesce", extra={"story_user_id": uid, "moment_key": plan.key[:60]})
            return await analyze(), None, None
        if time.monotonic() >= deadline:
            _metric(request, "BillingAnalysisInProgress", "moment")
            return None, None, _in_progress_response()
        await asyncio.sleep(0.4)
    # plan.action is analyze or refresh: this request owns the work
    try:
        value = await analyze()
    except BaseException:
        try:
            await run_in_threadpool(_abandon_analysis, led, uid, plan)
        except Exception as e:  # noqa: BLE001
            log.warning("billing_release_error", extra={"kind": "moment", "error": str(e)[:160]})
        raise
    try:
        await run_in_threadpool(_complete_analysis, led, uid, plan, to_json(value), version)
    except Exception as e:  # noqa: BLE001 — an unsettled hold is reclaimed after moment_stale_s; never fail the customer's response
        log.warning("billing_settle_error", extra={"kind": "moment", "error": str(e)[:160]})
    return value, None, None


# ---- read model --------------------------------------------------------------------------------------------------

# Contract-1 (B3) clients decode `offer.plus.videos` / `offer.plus.moments` as NON-optional Ints; dropping or nulling them makes the
# whole entitlement fail to decode (B5). They are kept ONLY for that decode and are not a limit: Plus is unlimited and nothing reads
# these numbers on the server. V2 clients read `offer.plus.unlimited`. shortcut: remove once no contract-1 build is in use.
_LEGACY_OFFER_VIDEOS, _LEGACY_OFFER_MOMENTS = 12, 100


def offer_payload() -> dict:
    """What a Plus subscription grants. Present in EVERY mode so the paywall can state it. The price is not here: Apple's StoreKit
    supplies the localized price."""
    from billing.apple import PLUS_PRODUCT_ID
    return {"plus": {"product_id": PLUS_PRODUCT_ID, "unlimited": True,
                     "videos": _LEGACY_OFFER_VIDEOS, "moments": _LEGACY_OFFER_MOMENTS}}


def _default_capabilities() -> dict:
    """Capabilities when no entitlement exists yet (nothing to read, or billing off): metered, never subscribed."""
    from billing.model import CAP_METERED, CAPABILITIES_VERSION
    return {"version": CAPABILITIES_VERSION, "video_generation": CAP_METERED, "moment_analysis": CAP_METERED,
            "subscription": {"status": "none", "ends_at": None}}


def entitlement_payload(request: Request, uid: str) -> dict:
    mode = billing_mode()
    base = {"contract_version": CONTRACT_VERSION, "billing_mode": mode, "enforced": mode == MODE_ENFORCE,
            "offer": offer_payload(), "capabilities": _default_capabilities()}
    led = _ledger(request)
    if led is None:
        # `off` (or unprovisioned). Meters are not read. When Apple purchases are possible (usage table configured) the app still
        # needs its appAccountToken to buy, and a Plus purchase must be visible after buying: identity token + a READ-ONLY view
        # of an entitlement that already exists (never created here).
        svc = apple_service(request)
        if svc is not None:
            try:
                base["apple_app_account_token"] = svc.ledger.get_or_create_apple_account_token(uid)
                existing = svc.ledger.entitlement_view(uid, create=False)
                if existing.get("plan"):
                    base = {**base, **{k: v for k, v in existing.items() if k not in ("contract_version",)}}
            except BillingStoreError:
                base["error"] = "billing_unavailable"
        return base
    try:
        view = led.entitlement_view(uid)
        if led.shadow and live_plus_active(request, uid):
            # observe: the shadow ledger is for hypothetical counters only; a paying subscriber must see the LIVE (Plus) view
            live = _live_ledger(request)
            if live is not None:
                view = live.entitlement_view(uid, create=False)
        token = led.get_or_create_apple_account_token(uid)   # identity item: same in observe and enforce
    except BillingStoreError:
        base["error"] = "billing_unavailable"
        return base
    return {**base, **view, "apple_app_account_token": token}


# ---- Apple (B2) --------------------------------------------------------------------------------------------------
# The Apple endpoints are independent of STORY_BILLING_MODE on purpose: a real purchase must be recorded whatever the rollout
# posture, and they always use the LIVE ledger (the shadow ledger is for hypothetical decisions only). They only change
# PLAN state (plan, status, period, allowances at the Apple period boundary); meters are still gated by the mode.

def apple_service(request: Request):
    """Returns the AppleBilling service, or None when the environment has no usage table (unprovisioned)."""
    ov = getattr(request.app.state, "_apple_billing_override", None)
    if ov is not None:
        return ov
    if not os.environ.get("STORY_USER_USAGE_TABLE", ""):
        return None
    svc = getattr(request.app.state, "_apple_billing", None)
    if svc is None:
        from billing.apple import AppleBilling, AppStoreVerifier, allowed_environments
        envs = allowed_environments(os.environ.get("STORY_ENVIRONMENT", "development"))
        svc = request.app.state._apple_billing = AppleBilling(BillingLedger(shadow=False), AppStoreVerifier(envs), environments=envs)
    return svc


def apple_error_response(e) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"error": e.code, "contract_version": CONTRACT_VERSION})
