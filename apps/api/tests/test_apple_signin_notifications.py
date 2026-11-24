"""D7: Sign in with Apple server-to-server notifications. Real RS256 JWTs from a throwaway key; no network."""
from __future__ import annotations

import json
import time

import jwt
import pytest
from app import apple_signin_notifications as asn
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
AUD = "com.lingzhang.story.signin.beta"


def token(etype="consent-revoked", sub="001234.abc", aud=AUD, iss=asn.APPLE_ISSUER, key=KEY, events_as_str=True):
    ev = {"type": etype, "sub": sub, "event_time": int(time.time() * 1000)}
    claims = {"iss": iss, "aud": aud, "iat": int(time.time()), "jti": "j1",
              "events": json.dumps(ev) if events_as_str else ev}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k"})


class Cognito:
    def __init__(self, users=("SignInWithApple_001234.abc",), fail=None):
        self.users, self.calls, self.fail = set(users), [], fail

    def admin_user_global_sign_out(self, UserPoolId, Username):
        self.calls.append(Username)
        if self.fail:
            raise self.fail
        if Username not in self.users:
            e = Exception("nf")
            e.response = {"Error": {"Code": "UserNotFoundException"}}
            raise e
        return {}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORY_ENVIRONMENT", "beta")
    monkeypatch.setenv("STORY_APPLE_SIGNIN_AUDIENCE", AUD)
    monkeypatch.setenv("STORY_COGNITO_USER_POOL_ID", "us-east-1_beta")
    monkeypatch.setattr(asn, "_apple_key", lambda t: KEY.public_key())
    app = create_app()
    cog = Cognito()
    app.state._apple_signin_cognito_override = cog
    c = TestClient(app)
    c.cognito = cog
    return c


def post(c, tok):
    return c.post("/v1/auth/apple-signin-notifications", json={"payload": tok})


def test_consent_revoked_signs_the_federated_user_out_without_a_token(client):
    r = post(client, token())
    assert r.status_code == 200 and r.json() == {"outcome": "signed_out"}
    assert client.cognito.calls == ["SignInWithApple_001234.abc"]


def test_account_delete_also_signs_out_and_events_may_be_an_object(client):
    assert post(client, token("account-delete", events_as_str=False)).json()["outcome"] == "signed_out"


def test_email_events_are_acknowledged_and_ignored(client):
    assert post(client, token("email-disabled")).json()["outcome"] == "ignored"
    assert client.cognito.calls == []


def test_unknown_user_is_acknowledged(client):
    assert post(client, token(sub="999.zzz")).json()["outcome"] == "no_user"


@pytest.mark.parametrize("kw", [{"key": OTHER}, {"aud": "com.someone.else"}, {"iss": "https://evil.example"}])
def test_bad_signature_audience_or_issuer_is_rejected_and_changes_nothing(client, kw):
    assert post(client, token(**kw)).status_code == 400
    assert client.cognito.calls == []


def test_missing_payload_is_400(client):
    assert client.post("/v1/auth/apple-signin-notifications", json={}).status_code == 400


def test_cognito_failure_is_503_so_apple_retries(client):
    client.cognito.fail = RuntimeError("throttled")
    assert post(client, token()).status_code == 503


def test_no_audience_configured_rejects_everything(client, monkeypatch):
    monkeypatch.setenv("STORY_APPLE_SIGNIN_AUDIENCE", "")
    assert post(client, token()).status_code == 400
