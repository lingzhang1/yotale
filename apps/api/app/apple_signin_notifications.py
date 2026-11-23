"""Sign in with Apple server-to-server notifications (account deletion design section 6, D7; Apple TN3194).

Apple POSTs `{"payload": "<JWT>"}` when a user stops using Sign in with Apple for the app (`consent-revoked`),
deletes their Apple Account (`account-delete`), or changes email forwarding (`email-disabled` / `email-enabled`).
The JWT is signed by Apple (keys at https://appleid.apple.com/auth/keys); `aud` is our Services ID and the
`events` claim is a JSON string with `type` and `sub` (the Apple user id).

Response to revocation (TN3194: "revert the client to an unauthenticated state"): global sign-out of the Cognito
user federated from that Apple id. That revokes refresh tokens, so the app signs out at its next refresh (within
the 60-minute access-token life). No data is deleted here: deleting data is the user's explicit in-app action, and
`account-delete` only tells us the Apple ID itself is gone.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Callable, Optional

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
REVOKING_EVENTS = {"consent-revoked", "account-delete"}
COGNITO_APPLE_PREFIX = "SignInWithApple_"


class InvalidNotification(Exception):
    """Signature, issuer, audience or shape check failed (HTTP 400; Apple does not retry a bad payload usefully)."""


def audiences() -> list[str]:
    raw = os.environ.get("STORY_APPLE_SIGNIN_AUDIENCE", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


_jwk_client = None


def _apple_key(token: str):
    global _jwk_client
    import jwt
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(APPLE_JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)
    return _jwk_client.get_signing_key_from_jwt(token).key


def verify(token: str, *, audience: list[str], key_for: Optional[Callable[[str], object]] = None) -> dict:
    """Verified `events` claim, or InvalidNotification."""
    import jwt
    if not audience:
        raise InvalidNotification("no audience configured")
    try:
        claims = jwt.decode(token, key=(key_for or _apple_key)(token), algorithms=["RS256"], issuer=APPLE_ISSUER, audience=audience,
                            options={"require": ["iss", "aud", "iat", "events"]})
    except Exception as e:  # noqa: BLE001 — any verification failure is a rejection
        raise InvalidNotification(type(e).__name__) from e
    events = claims["events"]
    if isinstance(events, str):
        try:
            events = json.loads(events)
        except ValueError as e:
            raise InvalidNotification("events not JSON") from e
    if not isinstance(events, dict) or not events.get("type") or not events.get("sub"):
        raise InvalidNotification("events missing type or sub")
    return events


def handle(events: dict, *, cognito, user_pool_id: str) -> str:
    """Apply one verified event. Returns an outcome code (logged; never the Apple user id)."""
    etype, sub = str(events["type"]), str(events["sub"])
    if etype not in REVOKING_EVENTS:
        return "ignored"
    if cognito is None or not user_pool_id:
        return "not_configured"
    username = COGNITO_APPLE_PREFIX + sub
    try:
        cognito.admin_user_global_sign_out(UserPoolId=user_pool_id, Username=username)
        return "signed_out"
    except Exception as e:  # noqa: BLE001
        code = ((getattr(e, "response", None) or {}).get("Error") or {}).get("Code") or type(e).__name__
        if code == "UserNotFoundException":
            return "no_user"          # never signed in here, or the account was already deleted
        raise


def sub_hash(events: dict) -> str:
    """Pseudonymous log handle for an event (first 12 hex of SHA-256 of the Apple sub)."""
    return hashlib.sha256(str(events.get("sub", "")).encode()).hexdigest()[:12]


def cognito_client(region: Optional[str] = None):
    import boto3
    return boto3.client("cognito-idp", region_name=region or os.environ.get("AWS_REGION", "us-east-1"))
