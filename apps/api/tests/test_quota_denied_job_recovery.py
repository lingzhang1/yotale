"""Regression: an async job DENIED at submit (operational quota) must never run later without authorization.

Before the fix the job row was created BEFORE the quota hold, a denial returned 429 but left the row `queued` and never enqueued, and
`reconcile_lost_enqueue` (which re-enqueues "stranded" queued jobs) would later enqueue and RUN it with no quota hold at all.
These tests use the REAL JobStore on DynamoDB Local (real conditional writes, real Scan filter), so they exercise the same
expressions production does. They are independent of `STORY_BILLING_MODE`: the fix applies in every mode, including OFF.
"""
from __future__ import annotations

import io
import json
import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import edit_plan_jobs as _jobs
from app.auth import CognitoConfig, CognitoJwtVerifier, IdentityStore
from app.main import create_app
from billing import ddb_local
from edit_plan_jobs import JobStore, JobStoreConfig
from user_quota import QuotaConfig, UserQuota
from user_quota.fakes import FakeDDB as QuotaFakeDDB

REGION, POOL, CLIENT_ID = "us-east-1", "us-east-1_TESTPOOL", "testclientid123"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"


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


class FakeSQS:
    def __init__(self):
        self.msgs = []

    def send_message(self, QueueUrl, MessageBody):
        self.msgs.append(json.loads(MessageBody)["job_id"])


class FakeS3:
    def __init__(self):
        self.obj = {}

    def put_object(self, Bucket, Key, Body, ContentType=None, ServerSideEncryption=None):
        self.obj[Key] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.obj[Key])}

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in self.obj if k.startswith(Prefix)]}

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.obj.pop(o["Key"], None)


@pytest.fixture()
def rig(ddb_local_endpoint, monkeypatch):
    for k, v in {"STORY_ENVIRONMENT": "beta", "STORY_COGNITO_USER_POOL_ID": POOL, "STORY_COGNITO_APP_CLIENT_ID": CLIENT_ID,
                 "STORY_EPIDEMIC_MODE": "prototyping", "STORY_QUOTA_MODE": "enforce", "STORY_THROTTLE_MODE": "observe"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)

    class R:
        pass

    r = R()
    c = ddb_local.client(ddb_local_endpoint)
    r.table = ddb_local.create_jobs_table(c)
    r.sqs, r.s3, r.ddb = FakeSQS(), FakeS3(), c
    r.store = JobStore(JobStoreConfig(table=r.table, queue_url="q", bucket="b", region="us-east-1"), ddb=c, sqs=r.sqs, s3=r.s3)
    r.quota = UserQuota(ddb=QuotaFakeDDB(), usage_table="t",
                        cfg=QuotaConfig(user_monthly_usd=50, user_daily_gens=500, max_active_jobs=1, global_monthly_usd=60))
    app = create_app()
    app.state._jwt_verifier_override = FakeVerifier()
    app.state._identity_store_override = FakeIdentity()
    app.state._job_store_override = r.store
    app.state._user_quota = r.quota
    r.client = TestClient(app)
    return r


def _edit(op):
    return {"operation_id": op, "sheet_order": "[]", "body": json.dumps({
        "story_id": "11111111-1111-4111-8111-111111111111", "creative_intent_id": "22222222-2222-4222-8222-222222222222",
        "creative_intent": {}, "moments": []})}


def _cov(op):
    return {"operation_id": op, "body": json.dumps({
        "story_id": "11111111-1111-4111-8111-111111111111", "story_guide": {}, "creative_intent": {}, "scope": {},
        "moment_understandings": [], "pending_count": 0})}


def _age(r, job_id, seconds=10_000):
    r.ddb.update_item(TableName=r.table, Key={"job_id": {"S": job_id}}, UpdateExpression="SET created_at = :t",
                      ExpressionAttributeValues={":t": {"N": str(int(time.time()) - seconds)}})


def _row(r, job_id):
    return r.store.get(job_id)


def _job_id(op, sub="u1"):
    return _jobs.job_id_for(f"story-{sub}\x1f{op}")


@pytest.mark.parametrize("mode", ["off", "observe"])
def test_a_quota_denied_edit_plan_job_is_terminal_and_the_reconciler_never_runs_it(rig, monkeypatch, mode):
    monkeypatch.setenv("STORY_BILLING_MODE", mode)
    first = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1"))
    assert first.status_code == 202
    denied = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2"))
    assert denied.status_code == 429 and denied.json()["error"] == "quota_exceeded"

    jid = _job_id("op-2")
    row = _row(rig, jid)
    assert row["status"] == "failed" and row["failure_category"] == "quota_denied"
    assert rig.sqs.msgs == [_job_id("op-1")]                                   # the denied job was never enqueued

    _age(rig, jid)                                                              # old enough for the lost-enqueue reconciler
    _age(rig, _job_id("op-1"))
    reenq = rig.store.reconcile_lost_enqueue()
    assert jid not in reenq and _job_id("op-1") in reenq                       # only the AUTHORIZED stranded job is re-enqueued
    assert rig.sqs.msgs.count(jid) == 0
    assert rig.store.claim_lease(jid) is None                                  # even a stray SQS message cannot start it
    assert _row(rig, jid)["status"] == "failed"
    assert rig.s3.list_objects_v2("b", f"jobs/{jid}")["Contents"] == [] if "jobs/" in "".join(rig.s3.obj) else True


def test_a_quota_denied_coverage_job_is_terminal_too(rig):
    assert rig.client.post("/v1/story-coverage/v2/jobs", headers=_auth(), data=_cov("c-1")).status_code == 202
    denied = rig.client.post("/v1/story-coverage/v2/jobs", headers=_auth(), data=_cov("c-2"))
    assert denied.status_code == 429
    jid = _job_id("c-2")
    assert _row(rig, jid)["status"] == "failed" and _row(rig, jid)["failure_category"] == "quota_denied"
    _age(rig, jid)
    assert jid not in rig.store.reconcile_lost_enqueue() and rig.store.claim_lease(jid) is None


def test_a_legitimate_retry_of_a_denied_operation_is_reopened_and_reserved_again(rig):
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1")).status_code == 202
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2")).status_code == 429
    jid = _job_id("op-2")
    # capacity frees: the first job finishes and releases its slot
    rig.quota.release_slot("story-u1", _job_id("op-1"))
    again = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2"))      # same client operation id
    assert again.status_code == 202 and again.json()["job_id"] == jid
    row = _row(rig, jid)
    assert row["status"] == "queued" and int(row.get("recovery_count", 0)) == 1
    assert "failure_category" not in row or not row.get("failure_category")
    assert rig.sqs.msgs.count(jid) == 1                                         # enqueued exactly once, now authorized
    assert rig.store.claim_lease(jid)                                          # and it may run


def test_a_denied_retry_stays_denied_and_is_never_enqueued(rig):
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1")).status_code == 202
    for _ in range(3):
        assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2")).status_code == 429
    jid = _job_id("op-2")
    assert _row(rig, jid)["status"] == "failed" and jid not in rig.sqs.msgs


def test_an_allowed_duplicate_submit_is_untouched_by_the_fix(rig):
    for _ in range(2):
        assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1")).status_code == 202
    assert rig.sqs.msgs == [_job_id("op-1")]                                   # one enqueue
    assert _row(rig, _job_id("op-1"))["status"] == "queued"                    # not terminalised


def test_only_a_still_queued_job_can_be_denied_a_running_one_is_never_failed_from_under_a_worker(rig):
    rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1"))
    jid = _job_id("op-1")
    token = rig.store.claim_lease(jid)
    assert token and rig.store.deny(jid, "quota_denied") is False
    assert _row(rig, jid)["status"] == "running"
    with pytest.raises(ValueError):
        rig.store.deny(jid, "internal")                                         # only denial categories are accepted


def test_the_denial_recovery_is_bounded(rig):
    rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1"))
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2")).status_code == 429
    jid = _job_id("op-2")
    rig.ddb.update_item(TableName=rig.table, Key={"job_id": {"S": jid}}, UpdateExpression="SET recovery_count = :n",
                        ExpressionAttributeValues={":n": {"N": str(_jobs.MAX_DENIAL_RECOVERIES)}})
    rig.quota.release_slot("story-u1", _job_id("op-1"))
    again = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2"))
    assert again.status_code == 202 and _row(rig, jid)["status"] == "failed"   # the cap stops the rewrite: a NEW operation id is needed
    assert jid not in rig.sqs.msgs


def test_a_denied_job_of_another_account_cannot_be_reopened_by_resubmitting(rig):
    rig.client.post("/v1/edit-plan-jobs", headers=_auth("u1"), data=_edit("op-1"))
    rig.client.post("/v1/edit-plan-jobs", headers=_auth("u1"), data=_edit("op-2"))
    rig.quota.release_slot("story-u1", _job_id("op-1"))
    other = rig.client.post("/v1/edit-plan-jobs", headers=_auth("u2"), data=_edit("op-2"))   # same client op id, other account
    assert other.status_code == 202 and other.json()["job_id"] != _job_id("op-2")           # a different job (ids are scoped)
    assert _row(rig, _job_id("op-2"))["status"] == "failed"


def test_the_existing_bounded_coverage_recovery_works_on_real_dynamodb_and_re_reserves_quota(rig, monkeypatch):
    """Found by the DynamoDB Local layer, two latent defects on the same path:
    1. `_recover_failed_coverage` used the reserved word `diagnostics` unaliased, so DynamoDB rejected the update
       (ValidationException) and a recoverable failed coverage job could never be re-attempted in production.
    2. After the worker released a failed job, its `released` slot/allowance markers stayed, so the re-opened job could never
       take a slot again (429 active_jobs) and its allowance looked already reserved. The worker now drops terminal markers."""
    from app import worker
    monkeypatch.setattr(worker, "_UserQuota", lambda usage_table="": rig.quota)
    monkeypatch.setenv("STORY_USER_USAGE_TABLE", "t")
    assert rig.client.post("/v1/story-coverage/v2/jobs", headers=_auth(), data=_cov("c-1")).status_code == 202
    jid = _job_id("c-1")
    assert rig.store.fail(jid, "provider_error", "provider outage")
    worker._quota_release_job(rig.store.get(jid), incurred_usd=0.0)            # exactly what the worker does on failure
    again = rig.client.post("/v1/story-coverage/v2/jobs", headers=_auth(), data=_cov("c-1"))
    assert again.status_code == 202 and again.json()["created"] is True
    row = _row(rig, jid)
    assert row["status"] == "queued" and int(row["recovery_count"]) == 1 and "failure_category" not in row
    from user_quota import _period
    item = rig.quota._ddb.items[("story-u1", _period())]
    assert item[f"slot#{jid}"]["M"]["state"]["S"] == "held" and float(item["active_jobs"]["N"]) == 1   # slot re-taken, cap intact
    assert float(item["reserved_usd"]["N"]) > 0                                                         # allowance re-reserved


def test_a_denied_submit_returns_its_allowance_and_a_retry_charges_it_exactly_once(rig):
    from user_quota import _period
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-1")).status_code == 202
    base = float(rig.quota._ddb.items[("story-u1", _period())]["reserved_usd"]["N"])
    for _ in range(3):
        assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2")).status_code == 429
        assert float(rig.quota._ddb.items[("story-u1", _period())]["reserved_usd"]["N"]) == base    # nothing leaked by denials
    g = rig.quota._ddb.items[("__global__", _period())]
    assert float(g["reserved_usd"]["N"]) == base                               # nor into the global breaker
    rig.quota.release_slot("story-u1", _job_id("op-1"))
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("op-2")).status_code == 202
    assert float(rig.quota._ddb.items[("story-u1", _period())]["reserved_usd"]["N"]) == base * 2   # exactly one new reservation


def test_a_billing_denied_job_is_terminal_never_reconciled_and_reopens_after_an_entitlement_grant(rig, monkeypatch):
    from billing import BillingLedger, PlanLimits, BillingConfig
    from billing.fakes import FakeDDB as BillingFake
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    app = rig.client.app
    app.state._user_quota = None                                                # isolate billing from the operational quota
    led = BillingLedger(ddb=BillingFake(), table="t", clock=lambda: 1_800_000_000,
                        cfg=BillingConfig(free_starter=PlanLimits(videos=1, moments=1)))
    app.state._billing_ledger_override = {"enforce": led}
    assert rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("v-1")).status_code == 202
    denied = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("v-2"))
    assert denied.status_code == 402 and denied.json()["error"] == "video_credits_exhausted"
    jid = _job_id("v-2")
    assert _row(rig, jid)["status"] == "failed" and _row(rig, jid)["failure_category"] == "billing_denied"
    _age(rig, jid)
    assert jid not in rig.store.reconcile_lost_enqueue() and rig.store.claim_lease(jid) is None
    led.admin_grant("story-u1", videos=5, moments=10, reason="support")          # entitlement changes
    ok = rig.client.post("/v1/edit-plan-jobs", headers=_auth(), data=_edit("v-2"))   # same operation id, now authorized
    assert ok.status_code == 202 and _row(rig, jid)["status"] == "queued" and rig.sqs.msgs.count(jid) == 1
