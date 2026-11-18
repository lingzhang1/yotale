"""Server-authoritative AU source binding and inference idempotency (pure logic over BillingLedger).

Problem: the client chooses `moment_id`, so a per-Moment-id charge can be dodged (resend an analysed id with new frames) and the same
frames can be analysed (and paid for at the provider) repeatedly. This module binds every analysis to SERVER-computed facts:

  fingerprint  sha256 over the frame bytes and timestamps the server actually accepted (computed here, never supplied)
  verified id  the account's own CLOUD-VERIFIED original media (media_store record, content sha256 checked by S3 against the full
               file). A client-supplied `content_sha256` is only a CLAIM: it counts as a source identity ONLY when the same
               account owns a cloud-verified media record for exactly that sha. A claim alone never grants reuse.

Record per (account, moment id, source):   billing#m#<moment id>~<f|v><24 hex>
    f<fingerprint>   frames-bound (always available, works before any upload: AU may precede cloud upload)
    v<verified sha>  bound to the authoritative original (stable across devices, reinstall and re-extraction of frames)

Decision (`plan_analysis`), evaluated against records that already exist, in this order:
  1. a SETTLED record at the CURRENT analysis version with a cached result  -> REUSE (no model call, no charge)
  2. a SETTLED record that is outdated or has no cached result             -> REFRESH (model call, NO new charge: already paid)
  3. a RESERVED record (someone else is analysing right now)               -> IN_FLIGHT (coalesce: wait for it, never a second call)
     (a reservation older than `moment_stale_s` is presumed dead and is taken over, still one charge)
  4. nothing                                                                -> ANALYZE under a NEW charge (BillingDenied when exhausted)
Same moment id with materially different frames and no verified common source has a different source id, so it falls to (4): it is a
new analysis and is charged. Cross-Story reuse is unaffected (the source id does not include the Story). Cross-account is isolated by the
partition key. Failed attempts release the reservation (no allowance consumed); their provider cost stays in `model_call_usage` and the
record keeps `b_fails` and the last correlation id.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .ledger import BillingLedger
from .model import Hold

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def frames_fingerprint(frames: Iterable[tuple[int, bytes]]) -> str:
    """sha256 over (count, then per frame: t_ms, length, bytes). Computed from the bytes the server accepted, so it cannot be
    claimed by the client. Order-sensitive on purpose (AU requires monotonically increasing timestamps)."""
    h = hashlib.sha256()
    h.update(b"au-frames/1")
    items = list(frames)
    h.update(len(items).to_bytes(4, "big"))
    for t_ms, data in items:
        h.update(int(t_ms).to_bytes(8, "big", signed=False))
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def normalize_claim(claim: Optional[str]) -> Optional[str]:
    c = (claim or "").strip().lower()
    return c if _HEX64.match(c) else None


@dataclass
class AnalysisPlan:
    action: str                         # reuse | refresh | analyze | in_flight
    key: str                            # the analysis record key (`<moment id>~<source id>`)
    reason: str = ""
    result: Optional[str] = None        # cached analysis JSON (action == reuse)
    hold: Optional[Hold] = None         # present for analyze
    bind: str = "frames"                # frames | cloud_verified
    owns_charge: bool = False


def source_keys(moment_id: str, fp: str, claim_sha: Optional[str], verified: bool) -> list[str]:
    mid = str(moment_id).strip().lower()
    keys = []
    claim = normalize_claim(claim_sha)
    if verified and claim:
        keys.append(f"{mid}~v{claim[:24]}")
    keys.append(f"{mid}~f{fp[:24]}")
    return keys


def plan_analysis(L: BillingLedger, uid: str, moment_id: str, *, fp: str, version: str, claim_sha: Optional[str] = None,
                  verified: bool = False, corr: str = "") -> AnalysisPlan:
    keys = source_keys(moment_id, fp, claim_sha, verified)
    views = {k: L.read_moment(uid, k) for k in keys}

    for k in keys:                                                      # 1 and 2: already paid for
        v = views[k]
        if v.get("state") in ("settled", "refunded"):
            if v.get("ver") == version and v.get("result"):
                return AnalysisPlan("reuse", k, "completed_identical_input", result=v["result"])
            if L.begin_refresh(uid, k, corr):
                return AnalysisPlan("refresh", k, "outdated_version" if v.get("ver") != version else "no_cached_result")
            return AnalysisPlan("in_flight", k, "refresh_in_progress")

    for k in keys:                                                      # 3: someone is analysing right now (or died)
        if views[k].get("state") == "reserved":
            hold = L.reserve_moment(uid, k)                             # a stale reservation is taken over, still one charge
            if hold.charged:
                return AnalysisPlan("analyze", k, "reclaimed_stale", hold=hold, owns_charge=True)
            return AnalysisPlan("in_flight", k, "identical_in_flight")

    primary = keys[0]                                                   # 4: a new, charged analysis
    bind = "cloud_verified" if primary.split("~", 1)[1].startswith("v") else "frames"
    attrs = {"b_fp": {"S": fp}, "b_bind": {"S": bind}, "b_corr": {"S": (corr or "-")[:64]}}
    claim = normalize_claim(claim_sha)
    if claim:
        attrs["b_claim"] = {"S": claim}                                 # recorded as a CLAIM; never used as identity by itself
    hold = L.reserve_moment(uid, primary, attrs=attrs)                  # may raise BillingDenied (typed)
    if hold.charged:
        return AnalysisPlan("analyze", primary, "new_source", hold=hold, bind=bind, owns_charge=True)
    if hold.reason == "unlimited":
        return AnalysisPlan("analyze", primary, "unlimited", hold=hold, bind=bind)
    return AnalysisPlan("in_flight", primary, "raced")                  # settled or reserved by a concurrent identical request


def complete(L: BillingLedger, uid: str, plan: AnalysisPlan, result_json: str, version: str) -> None:
    """Persist a SUCCESSFUL analysis: settle the charge (analyze) or finish the refresh, and cache the result."""
    if plan.action == "analyze" and plan.owns_charge:
        L.settle_moment(uid, plan.key, result=result_json, version=version)
    elif plan.action == "refresh":
        L.finish_refresh(uid, plan.key, result_json, version)


def abandon(L: BillingLedger, uid: str, plan: AnalysisPlan) -> None:
    """A FAILED analysis: give the allowance back (analyze) or release the refresh claim. Only the owner of the charge releases."""
    if plan.action == "analyze" and plan.owns_charge:
        L.release_moment(uid, plan.key)
    elif plan.action == "refresh":
        L.abort_refresh(uid, plan.key)
