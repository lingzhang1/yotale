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

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.throttle import ROUTE_CLASS

try:
    from billing import (
        BillingDenied, BillingLedger, BillingStoreError, CONTRACT_VERSION, Hold, MODE_ENFORCE, MODE_OBSERVE, MODE_OFF,
        billing_mode,
    )
except Exception:  # pragma: no cover - import-safe when the package is not bundled
    BillingLedger = None  # type: ignore

    def billing_mode() -> str:  # type: ignore
        return "off"

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
    if mode == MODE_OFF or BillingLedger is None:
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


def _reserve(request: Request, kind: str, uid: str, key: str):
    """Returns (gate | None, response | None). `response` is set only in enforce mode and is the 402/503 to return."""
    led = _ledger(request)
    if led is None:
        return None, None
    enforce = billing_mode() == MODE_ENFORCE
    try:
        hold = led.reserve_video(uid, key) if kind == "video" else led.reserve_moment(uid, key)
    except BillingDenied as d:
        if enforce:
            _metric(request, "BillingDenied", kind)
            log.info("billing_denied", extra={"kind": kind, "code": d.code, "story_user_id": uid})
            return None, denial_response(d)
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


def reserve_moment(request: Request, uid: str, moment_id: str):
    return _reserve(request, "moment", uid, moment_id)


def settle(gate: Optional[Gate]) -> None:
    """Spend the held unit. Never raises into the response: an unsettled hold is reconciled by the job sweep / stale
    reclaim, and an under-charge is preferred to a failed customer response."""
    if gate is None:
        return
    try:
        if gate.kind == "video":
            gate.ledger.settle_video(gate.uid, gate.key)
        else:
            gate.ledger.settle_moment(gate.uid, gate.key)
    except Exception as e:  # noqa: BLE001
        log.warning("billing_settle_error", extra={"kind": gate.kind, "error": str(e)[:160]})


def release(gate: Optional[Gate]) -> None:
    """Return a held unit after a failed operation. Only the call that OWNS the charge releases it, so a duplicate
    in-flight request failing cannot refund a charge that another request is still earning."""
    if gate is None or not gate.owns_charge:
        return
    try:
        if gate.kind == "video":
            gate.ledger.release_video(gate.uid, gate.key)
        else:
            gate.ledger.release_moment(gate.uid, gate.key)
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


# ---- read model --------------------------------------------------------------------------------------------------

def entitlement_payload(request: Request, uid: str) -> dict:
    mode = billing_mode()
    base = {"contract_version": CONTRACT_VERSION, "billing_mode": mode, "enforced": mode == MODE_ENFORCE}
    led = _ledger(request)
    if led is None:
        return base
    try:
        view = led.entitlement_view(uid)
        if not led.shadow:
            led.reclaim_stale_moments(uid)      # opportunistic, best-effort, needs dynamodb:Query
        token = led.get_or_create_apple_account_token(uid)   # identity item: same in observe and enforce
    except BillingStoreError:
        base["error"] = "billing_unavailable"
        return base
    return {**base, **view, "apple_app_account_token": token}
