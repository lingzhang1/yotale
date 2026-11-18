"""AU source binding and inference idempotency (Billing V1), through the real endpoint, on the in-memory double AND DynamoDB Local.

The charge and any reuse are decided from the frames the SERVER accepted and the account's own cloud-verified media, never from the
client-chosen moment id (or a client-supplied content sha) alone."""
from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from PIL import Image

import observability
from app import billing_gate
from app.auth import CognitoConfig, CognitoJwtVerifier, IdentityStore
from app.deps import get_asset_understanding_engine
from app.main import create_app
from asset_engine import DEFAULT_AU_MODEL, RealAssetUnderstandingEngine
from billing import BillingConfig, BillingLedger, PlanLimits
from billing.analysis import frames_fingerprint, plan_analysis
from media_store import STATE_CLOUD_VERIFIED, STATE_UPLOADING, cloud_media_id_for
from model_gateway import FakeModelGateway, ProviderError
from model_gateway.openai_gateway import OpenAIModelGateway

REGION, POOL, CLIENT_ID = "us-east-1", "us-east-1_TESTPOOL", "testclientid123"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"
T0 = 1_800_000_000
SHA_X = "ab" * 32
SHA_Y = "cd" * 32


def _make_key():
    import jwt.algorithms
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "kidA", "alg": "RS256", "use": "sig"})
    return key, jwk


KEY, JWK = _make_key()


def _auth(sub="u1"):
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iss": ISSUER, "token_use": "access", "client_id": CLIENT_ID, "iat": now, "exp": now + 3600},
                     KEY, algorithm="RS256", headers={"kid": "kidA"})
    return {"Authorization": f"Bearer {tok}"}


class FakeVerifier(CognitoJwtVerifier):
    def __init__(self):
        super().__init__(CognitoConfig(region=REGION, user_pool_id=POOL, app_client_id=CLIENT_ID))

    def _fetch_jwks(self):
        return {"keys": [JWK]}


class FakeIdentity(IdentityStore):
    def __init__(self):
        super().__init__(claims_table="t", users_table="u")

    def resolve(self, cognito_sub, *, verified_email=None):
        return f"story-{cognito_sub}"


class FakeMedia:
    """media_store double: an account's media records, keyed exactly like the real store (owner, uuid5(owner + sha))."""
    def __init__(self):
        self.recs = {}

    def add(self, owner, sha, state=STATE_CLOUD_VERIFIED):
        self.recs[(owner, cloud_media_id_for(owner, sha))] = {"state": state, "content_sha256": sha}

    def get(self, owner, cloud_media_id):
        return self.recs.get((owner, cloud_media_id))


class CountingGateway(FakeModelGateway):
    def __init__(self, response, delay=0.0, fail=False):
        super().__init__(response=response)
        self.delay, self.fail, self.n, self._lock = delay, fail, 0, threading.Lock()

    def generate_structured(self, req):
        with self._lock:
            self.n += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise ProviderError("provider down")
        return super().generate_structured(req)


_GOOD = {
    "observed": {"summary": "A quiet meal.", "subjects": ["meal"],
                 "events": [{"start_time": 0.0, "end_time": 20.0, "description": "eating"}],
                 "temporal_order_note": "sustained", "useful_segments": [{"start_time": 0.0, "end_time": 20.0, "why_useful": "calm"}]},
    "story_context": {"story_utility": "strong_elsewhere", "requested_shot_contribution": "fulfilled",
                      "requested_beat_contribution": "serves beat_endofday"},
}


def _jpeg(shade):
    b = io.BytesIO()
    Image.new("RGB", (24, 24), (shade, 110, 130)).save(b, format="JPEG")
    return b.getvalue()


def frames_of(shade):
    return [(i * 100, _jpeg(shade)) for i in range(24)]


def mid(i=1):
    return f"00000000-0000-4000-8000-{i:012d}"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k, v in {"STORY_ENVIRONMENT": "beta", "STORY_COGNITO_USER_POOL_ID": POOL, "STORY_COGNITO_APP_CLIENT_ID": CLIENT_ID,
                 "STORY_EPIDEMIC_MODE": "prototyping", "STORY_QUOTA_MODE": "observe", "STORY_THROTTLE_MODE": "observe"}.items():
        monkeypatch.setenv(k, v)
    for k in ("STORY_USER_USAGE_TABLE", "STORY_BILLING_MODE", "STORY_MEDIA_TABLE"):
        monkeypatch.delenv(k, raising=False)


class Rig:
    def __init__(self, usage_backend, mode="enforce", gateway=None, cfg=None):
        self.ddb, self.table, self.kind = usage_backend
        self.t = [T0]
        clock = lambda: self.t[0]  # noqa: E731
        self.cfg = cfg or BillingConfig(analysis_wait_s=3.0)
        self.live = BillingLedger(ddb=self.ddb, table=self.table, cfg=self.cfg, clock=clock)
        self.shadow = BillingLedger(ddb=self.ddb, table=self.table, cfg=self.cfg, shadow=True, clock=clock)
        os.environ["STORY_BILLING_MODE"] = mode
        self.app = create_app()
        self.app.state._jwt_verifier_override = FakeVerifier()
        self.app.state._identity_store_override = FakeIdentity()
        self.app.state._billing_ledger_override = {"observe": self.shadow, "enforce": self.live}
        self.media = FakeMedia()
        self.app.state._media_store_override = self.media
        self.gw = gateway or CountingGateway(_GOOD)
        engine = RealAssetUnderstandingEngine(self.gw, model_id=DEFAULT_AU_MODEL)
        self.app.dependency_overrides[get_asset_understanding_engine] = lambda: engine

    def _files(self, frames):
        return ([("frames", (f"f{i}.jpg", data, "image/jpeg")) for i, (_t, data) in enumerate(frames)],
                json.dumps([{"t_ms": t} for t, _d in frames]))

    async def post(self, client, moment, frames, sub="u1", claim=None):
        files, fmeta = self._files(frames)
        meta = {"moment_id": moment}
        if claim:
            meta["content_sha256"] = claim
        return await client.post("/v1/asset-understanding", headers=_auth(sub),
                                 data={"meta": json.dumps(meta), "frames_meta": fmeta}, files=files)

    def run(self, coro_fn):
        async def main():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://t") as c:
                return await coro_fn(c)
        return asyncio.run(main())

    def one(self, moment, frames, sub="u1", claim=None):
        return self.run(lambda c: self.post(c, moment, frames, sub, claim))

    def ent(self, sub="u1"):
        return self.live.get_entitlement(f"story-{sub}")


# ---- same id / same frames ---------------------------------------------------------------------------------------

def test_same_id_same_frames_reuses_the_completed_result_without_a_second_model_call(usage_backend):
    r = Rig(usage_backend)
    a = r.one(mid(), frames_of(90))
    b = r.one(mid(), frames_of(90))
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()                                             # byte-identical result
    assert r.gw.n == 1                                                      # the model ran once
    e = r.ent()
    assert (e.m_used, e.m_avail, e.m_resv) == (1, 29, 0)


def test_the_same_source_used_by_several_stories_is_analysed_and_charged_once(usage_backend):
    r = Rig(usage_backend)
    for _ in range(3):                                                      # AU requests carry no Story id: three Stories, one Moment
        assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.gw.n == 1 and r.ent().m_used == 1


# ---- same id / different frames ----------------------------------------------------------------------------------

def test_same_id_with_materially_different_frames_is_a_new_charged_analysis(usage_backend):
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.one(mid(), frames_of(200)).status_code == 200                  # different bytes under the same id
    assert r.gw.n == 2                                                      # NOT a free second analysis
    assert r.ent().m_used == 2
    assert r.one(mid(), frames_of(200)).status_code == 200                  # ... but then identical input reuses again
    assert r.gw.n == 2 and r.ent().m_used == 2


def test_a_client_sha_claim_alone_never_grants_reuse(usage_backend):
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200
    assert r.one(mid(), frames_of(200), claim=SHA_X).status_code == 200     # same claim, different frames, nothing verified
    assert r.gw.n == 2 and r.ent().m_used == 2


def test_a_claim_naming_another_accounts_verified_media_does_not_verify(usage_backend):
    r = Rig(usage_backend)
    r.media.add("story-u2", SHA_X)                                          # u2 genuinely owns a verified original with this sha
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200      # u1 claims it
    assert r.one(mid(), frames_of(200), claim=SHA_X).status_code == 200
    assert r.gw.n == 2 and r.ent().m_used == 2                              # no cross-account verification


# ---- concurrency -------------------------------------------------------------------------------------------------

def test_concurrent_identical_submissions_coalesce_into_one_model_call_one_charge(usage_backend):
    r = Rig(usage_backend, gateway=CountingGateway(_GOOD, delay=0.5))

    async def go(c):
        return await asyncio.gather(*(r.post(c, mid(), frames_of(90)) for _ in range(6)))

    resps = r.run(go)
    assert [x.status_code for x in resps] == [200] * 6
    assert len({json.dumps(x.json(), sort_keys=True) for x in resps}) == 1
    assert r.gw.n == 1
    e = r.ent()
    assert (e.m_used, e.m_resv, e.m_avail) == (1, 0, 29)


def test_concurrent_distinct_moments_each_run_once_and_the_allowance_cap_holds(usage_backend):
    r = Rig(usage_backend, gateway=CountingGateway(_GOOD, delay=0.15),
            cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=3), analysis_wait_s=3.0))

    async def go(c):
        return await asyncio.gather(*(r.post(c, mid(i), frames_of(80 + i)) for i in range(8)))

    codes = sorted(x.status_code for x in r.run(go))
    assert codes == [200] * 3 + [402] * 5
    e = r.ent()
    assert (e.m_used, e.m_resv, e.m_avail) == (3, 0, 0) and r.gw.n == 3


# ---- failure, timeout and retry ----------------------------------------------------------------------------------

def test_a_failed_analysis_consumes_nothing_but_its_cost_is_recorded(usage_backend, monkeypatch):
    lines = []

    class Cap:
        def info(self, msg, extra=None):
            lines.append((msg, extra or {}))

    monkeypatch.setattr(observability, "get_logger", lambda name="story", level=20: Cap())
    no_tool = {"choices": [{"finish_reason": "stop", "message": {}}],
               "usage": {"prompt_tokens": 30000, "completion_tokens": 600, "total_tokens": 30600}}
    gw = OpenAIModelGateway("gpt-5.1", api_key="k", http_post=lambda url, h, b, t: (200, json.dumps(no_tool).encode(), {}))
    r = Rig(usage_backend, gateway=gw)
    resp = r.one(mid(), frames_of(90))
    assert resp.status_code == 503
    e = r.ent()
    assert (e.m_used, e.m_resv, e.m_avail) == (0, 0, 30)                    # allowance returned
    billed = [x for m, x in lines if m == "model_call_usage"]
    assert billed and all(x["input_tokens"] == 30000 and x["estimated_cost_usd"] > 0 for x in billed)   # provider cost still recorded
    assert all(x["story_user_id"] == "story-u1" and x.get("correlation_id") for x in billed)
    rec = r.live.read_moment("story-u1", f"{mid()}~f{frames_fingerprint(frames_of(90))[:24]}")
    assert rec["state"] == "released" and rec["fails"] == 1 and rec["corr"] == billed[0]["correlation_id"]


def test_provider_failure_then_retry_charges_exactly_once(usage_backend):
    r = Rig(usage_backend, gateway=CountingGateway(_GOOD, fail=True))
    assert r.one(mid(), frames_of(90)).status_code == 503
    assert r.ent().m_used == 0
    r.gw.fail = False
    assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.one(mid(), frames_of(90)).status_code == 200
    e = r.ent()
    assert (e.m_used, e.m_resv, e.m_avail) == (1, 0, 29)


def test_an_owner_that_died_mid_analysis_is_taken_over_without_a_second_charge(usage_backend):
    r = Rig(usage_backend, cfg=BillingConfig(analysis_wait_s=0.6))
    fp = frames_fingerprint(frames_of(90))
    dead = plan_analysis(r.live, "story-u1", mid(), fp=fp, version="v", corr="dead-request")   # reserved, then the process died
    assert dead.action == "analyze"
    t0 = time.monotonic()
    waiting = r.one(mid(), frames_of(90))
    assert waiting.status_code == 503 and waiting.json()["error"] == "analysis_in_progress"   # bounded wait, no second model call
    assert time.monotonic() - t0 < 5 and r.gw.n == 0
    r.t[0] += r.cfg.moment_stale_s + 1                                       # the reservation is now presumed dead
    ok = r.one(mid(), frames_of(90))
    assert ok.status_code == 200 and r.gw.n == 1
    e = r.ent()
    assert (e.m_used, e.m_resv, e.m_avail) == (1, 0, 29)                     # still ONE unit for the whole sequence


# ---- isolation ---------------------------------------------------------------------------------------------------

def test_cross_account_isolation_one_accounts_result_is_never_served_to_another(usage_backend):
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90), sub="u1").status_code == 200
    assert r.one(mid(), frames_of(90), sub="u2").status_code == 200          # same id AND same frames, different account
    assert r.gw.n == 2
    assert r.ent("u1").m_used == 1 and r.ent("u2").m_used == 1
    assert r.one(mid(), frames_of(90), sub="u1").status_code == 200 and r.gw.n == 2


# ---- cloud verification order ------------------------------------------------------------------------------------

def test_cloud_verification_before_au_binds_to_the_authoritative_source_across_devices(usage_backend):
    r = Rig(usage_backend)
    r.media.add("story-u1", SHA_X)                                           # original already uploaded and S3-verified
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200       # device A
    again = r.one(mid(), frames_of(200), claim=SHA_X)                        # device B / reinstall: frames re-extracted differently
    assert again.status_code == 200
    assert r.gw.n == 1 and r.ent().m_used == 1                               # same verified original => reused, one charge


def test_an_uploading_or_unverified_record_does_not_count_as_verified(usage_backend):
    r = Rig(usage_backend)
    r.media.add("story-u1", SHA_X, state=STATE_UPLOADING)
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200
    assert r.one(mid(), frames_of(200), claim=SHA_X).status_code == 200
    assert r.gw.n == 2 and r.ent().m_used == 2


def test_au_before_cloud_verification_still_works_and_later_verification_does_not_double_charge(usage_backend):
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200       # AU runs before any upload
    assert r.ent().m_used == 1
    r.media.add("story-u1", SHA_X)                                           # the upload completes and verifies later
    again = r.one(mid(), frames_of(90), claim=SHA_X)                         # same device, identical frames
    assert again.status_code == 200 and r.gw.n == 1 and r.ent().m_used == 1


def test_a_different_verified_original_under_the_same_id_is_a_new_source(usage_backend):
    r = Rig(usage_backend)
    r.media.add("story-u1", SHA_X)
    r.media.add("story-u1", SHA_Y)
    assert r.one(mid(), frames_of(90), claim=SHA_X).status_code == 200
    assert r.one(mid(), frames_of(90), claim=SHA_Y).status_code == 200       # identical frames but a different verified original
    assert r.gw.n == 2 and r.ent().m_used == 2


# ---- analysis version ---------------------------------------------------------------------------------------------

def test_an_analysis_version_upgrade_re_analyses_without_a_new_charge(usage_backend, monkeypatch):
    import app.main as main
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90)).status_code == 200
    monkeypatch.setattr(main, "AU_PROMPT_VERSION", "au_prompt/NEXT")         # the platform ships a new analysis version
    assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.gw.n == 2                                                       # the stale result is not served
    assert r.ent().m_used == 1                                               # already paid: no second allowance unit
    assert r.one(mid(), frames_of(90)).status_code == 200 and r.gw.n == 2    # the upgraded result is now the reusable one


def test_a_refresh_failure_keeps_the_paid_record_and_the_old_result(usage_backend, monkeypatch):
    import app.main as main
    r = Rig(usage_backend)
    assert r.one(mid(), frames_of(90)).status_code == 200
    monkeypatch.setattr(main, "AU_PROMPT_VERSION", "au_prompt/NEXT")
    r.gw.fail = True
    assert r.one(mid(), frames_of(90)).status_code == 503
    assert r.ent().m_used == 1
    r.gw.fail = False
    assert r.one(mid(), frames_of(90)).status_code == 200                    # the claim was released: the retry can refresh


# ---- observe mode is shadow-only ----------------------------------------------------------------------------------

def test_observe_mode_always_analyses_never_reuses_and_never_touches_live_state(usage_backend):
    r = Rig(usage_backend, mode="observe")
    for _ in range(3):
        assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.gw.n == 3                                                       # customer behaviour is unchanged
    assert r.live.get_entitlement("story-u1") is None
    s = r.shadow.get_entitlement("story-u1")
    assert s is not None and s.m_used == 1                                   # the shadow ledger shows the hypothetical decision


def test_off_mode_touches_no_billing_state(usage_backend):
    r = Rig(usage_backend, mode="off")
    for _ in range(2):
        assert r.one(mid(), frames_of(90)).status_code == 200
    assert r.gw.n == 2
    assert r.live.get_entitlement("story-u1") is None and r.shadow.get_entitlement("story-u1") is None


def test_the_fingerprint_depends_on_bytes_timestamps_and_order():
    base = frames_of(90)
    assert frames_fingerprint(base) == frames_fingerprint(list(base))
    assert frames_fingerprint(base) != frames_fingerprint(frames_of(91))
    assert frames_fingerprint(base) != frames_fingerprint([(t + 1, d) for t, d in base])
    assert frames_fingerprint(base) != frames_fingerprint(list(reversed(base)))
    assert frames_fingerprint(base) != frames_fingerprint(base[:-1])
