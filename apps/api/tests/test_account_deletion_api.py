"""Account deletion D3: routes, the path-scoped status gate, error codes, fail-closed identity, guards G1/G2.

Real RS256 tokens from a throwaway key; the REAL IdentityStore and RequestStore run on the account-deletion
multi-table DynamoDB fake (real expression evaluation). No AWS.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid

import account_deletion.config as C
import jwt
import pytest
from account_deletion import RequestStore
from account_deletion.fakes import FakeDDB
from app.auth import CognitoConfig, CognitoJwtVerifier, IdentityStore
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

REGION, POOL, CLIENT = "us-east-1", "us-east-1_TESTPOOL", "client123"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"


def _key():
    import jwt.algorithms
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(k.public_key()))
    pub.update(kid="k1", alg="RS256", use="sig")
    return k, pub


KEY, JWK = _key()


def token(sub="sub-a", auth_time: object = "now"):
    now = int(time.time())
    claims = {"sub": sub, "iss": ISSUER, "token_use": "access", "client_id": CLIENT, "iat": now, "exp": now + 3600}
    if auth_time == "now":
        claims["auth_time"] = now
    elif auth_time is not None:
        claims["auth_time"] = auth_time
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "k1"})}


class Verifier(CognitoJwtVerifier):
    def __init__(self):
        super().__init__(CognitoConfig(region=REGION, user_pool_id=POOL, app_client_id=CLIENT))

    def _fetch_jwks(self):
        return {"keys": [JWK]}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("STORY_ENVIRONMENT", "development")
    monkeypatch.setenv("STORY_REQUIRE_AUTH", "1")
    monkeypatch.delenv("STORY_ACCOUNT_DELETIONS_TABLE", raising=False)
    ddb = FakeDDB()
    app = create_app()
    app.state._jwt_verifier_override = Verifier()
    app.state._identity_store_override = IdentityStore(ddb=ddb, claims_table="claims", users_table="users",
                                                       region=REGION)
    store = RequestStore(ddb, C.fake_config())
    app.state._deletion_store_override = store

    class E:
        pass
    e = E()
    e.client, e.ddb, e.store, e.app = TestClient(app), ddb, store, app
    return e


def body(rid=None, secret="ab" * 32, confirm="DELETE"):
    rid = rid or str(uuid.uuid4())
    return {"confirm": confirm, "request_id": rid, "receipt_hash": hashlib.sha256(secret.encode()).hexdigest()}, rid


def me(env, sub="sub-a"):
    return env.client.get("/v1/me", headers=token(sub))


def uid_of(env, sub="sub-a"):
    return me(env, sub).json()["story_user_id"]


def test_accept_flips_the_account_and_is_idempotent(env):
    uid = uid_of(env)
    b, rid = body()
    r = env.client.post("/v1/account/deletion", json=b, headers=token())
    assert r.status_code == 202 and r.json() == {"state": "accepted", "completed_at": None, "request_id": rid}
    assert env.ddb.tables["users"][(uid, "")]["account_status"]["S"] == "deleting"
    assert env.store.get(uid)["request_id"] == rid
    # the deletion routes still admit a `deleting` account: a retry is idempotent, a new id conflicts
    assert env.client.post("/v1/account/deletion", json=b, headers=token()).status_code == 202
    b2, _ = body()
    r2 = env.client.post("/v1/account/deletion", json=b2, headers=token())
    assert r2.status_code == 409 and r2.json()["error"] == "deletion_already_requested"
    g = env.client.get("/v1/account/deletion", headers=token())
    assert g.status_code == 200 and g.json()["request_id"] == rid


def test_every_other_route_refuses_a_deleting_account_with_a_stable_code(env):
    uid_of(env)
    b, _ = body()
    env.client.post("/v1/account/deletion", json=b, headers=token())
    r = me(env)
    assert r.status_code == 403 and r.json() == {"detail": "account deleting", "error": "account_deletion_in_progress"}
    assert env.client.get("/v1/stories", headers=token()).json().get("error") == "account_deletion_in_progress"


def test_deleted_account_is_refused_everywhere_including_the_deletion_routes(env):
    uid = uid_of(env)
    env.ddb.tables["users"][(uid, "")]["account_status"] = {"S": "deleted"}
    for r in (me(env), env.client.get("/v1/account/deletion", headers=token()),
              env.client.post("/v1/account/deletion", json=body()[0], headers=token())):
        assert r.status_code == 403 and r.json()["error"] == "account_deleted"


def test_suspended_account_gets_403_without_a_deletion_code(env):
    uid = uid_of(env)
    env.ddb.tables["users"][(uid, "")]["account_status"] = {"S": "suspended"}
    r = env.client.post("/v1/account/deletion", json=body()[0], headers=token())
    assert r.status_code == 403 and "error" not in r.json()      # generic: never triggers a device wipe


def test_claim_without_a_users_row_fails_closed(env):
    uid = uid_of(env)
    env.ddb.tables["users"].pop((uid, ""))
    r = me(env)
    assert r.status_code == 403 and r.json()["detail"] == "account missing"


@pytest.mark.parametrize("auth_time", [None, int(time.time()) - 301])
def test_requires_a_fresh_sign_in(env, auth_time):
    uid_of(env)
    r = env.client.post("/v1/account/deletion", json=body()[0], headers=token(auth_time=auth_time))
    assert r.status_code == 401 and r.json() == {"error": "reauth_required"}
    assert env.store.get(uid_of(env)) is None


def test_validation(env):
    uid_of(env)
    assert env.client.post("/v1/account/deletion", json=body(confirm="delete")[0], headers=token()).json() == \
        {"error": "confirm_required"}
    bad, _ = body(rid="not-a-uuid")
    assert env.client.post("/v1/account/deletion", json=bad, headers=token()).status_code == 422
    v1 = body(rid=str(uuid.uuid1()))[0]
    assert env.client.post("/v1/account/deletion", json=v1, headers=token()).status_code == 422
    assert env.client.post("/v1/account/deletion", json={**body()[0], "uid": "x"}, headers=token()).status_code == 422
    assert env.client.post("/v1/account/deletion", json=body()[0]).status_code == 401      # no token


def test_fails_closed_without_the_table_and_on_an_unknown_outcome(env, monkeypatch):
    uid_of(env)
    env.app.state._deletion_store_override = None
    r = env.client.post("/v1/account/deletion", json=body()[0], headers=token())
    assert r.status_code == 503 and r.json()["error"] == "deletion_unavailable"
    env.app.state._deletion_store_override = env.store
    env.ddb.fail_next["transact_write_items"] = RuntimeError("throttled")
    r = env.client.post("/v1/account/deletion", json=body()[0], headers=token())
    assert r.status_code == 503 and r.json()["error"] == "deletion_outcome_unknown"


def test_public_status_route_needs_no_token_and_reveals_nothing_without_the_secret(env):
    uid_of(env)
    secret = "cd" * 32
    b, rid = body(secret=secret)
    env.client.post("/v1/account/deletion", json=b, headers=token())
    ok = env.client.post("/v1/account/deletion/status", json={"request_id": rid, "receipt_secret": secret})
    assert ok.status_code == 200 and ok.json() == {"state": "accepted", "completed_at": None}
    wrong = env.client.post("/v1/account/deletion/status", json={"request_id": rid, "receipt_secret": "ef" * 32})
    unknown = env.client.post("/v1/account/deletion/status",
                              json={"request_id": str(uuid.uuid4()), "receipt_secret": secret})
    malformed = env.client.post("/v1/account/deletion/status", json={"request_id": rid, "receipt_secret": "x"})
    assert wrong.status_code == unknown.status_code == malformed.status_code == 404
    assert wrong.json() == unknown.json() == malformed.json() == {"error": "not_found"}


def test_status_route_is_public_and_post_deletion_is_throttled_as_its_own_class():
    from app.auth import DELETION_ROUTES, PUBLIC_ROUTES
    from app.throttle import CLASS_POLICIES, ROUTE_CLASS
    assert ("POST", "/v1/account/deletion/status") in PUBLIC_ROUTES
    assert ("POST", "/v1/account/deletion") not in PUBLIC_ROUTES
    assert DELETION_ROUTES == {("POST", "/v1/account/deletion"), ("GET", "/v1/account/deletion")}
    assert ROUTE_CLASS[("POST", "/v1/account/deletion")] == "account_deletion"
    assert CLASS_POLICIES["account_deletion"].default_per_min == 3


def test_worker_completes_a_request_accepted_through_the_api(env):
    """End to end on the fake: API accept -> scheduled worker -> completed; receipt status says completed."""
    from account_deletion import Worker
    from account_deletion.fakes import FakeCognito, FakeS3
    uid = uid_of(env)
    env.ddb.tables["users"][(uid, "")]["cognito_sub"] = {"S": "sub-a"}
    secret = "12" * 32
    b, rid = body(secret=secret)
    assert env.client.post("/v1/account/deletion", json=b, headers=token()).status_code == 202
    cog = FakeCognito(sub_is_username=True)
    cog.add("sub-a", "sub-a")
    clock = {"t": time.time()}
    w = Worker(C.fake_config(), env.ddb, FakeS3(), cog, clock=lambda: clock["t"], emit=lambda *a: None,
               log=lambda r: None)
    for _ in range(12):
        w.run("r")
        req = env.store.get(uid)
        if req["state"] == C.STATE_COMPLETED:
            break
        clock["t"] = max(clock["t"], req["next_run_at"])
    st = env.client.post("/v1/account/deletion/status", json={"request_id": rid, "receipt_secret": secret}).json()
    assert st["state"] == "completed" and "sub-a" not in cog.users
    assert me(env).json()["error"] == "account_deleted"
