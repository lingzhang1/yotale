"""Mint a TEST Apple-style certificate chain and signed JWS so the REAL verifier path (x5c chain -> root, ES256 signature,
bundle, environment, Apple marker OIDs) runs in tests without Apple. The test root replaces Apple's root in the verifier; the
production roots are pinned separately in test_apple_verifier.py."""
from __future__ import annotations

import base64
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier

LEAF_OID = ObjectIdentifier("1.2.840.113635.100.6.11.1")           # Mac App Store Receipt Signing marker
INTERMEDIATE_OID = ObjectIdentifier("1.2.840.113635.100.6.2.1")    # WWDR intermediate marker


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, pub, signer, *, ca: bool, marker=None, days=3650):
    issuer_pub = signer.public_key()
    now = dt.datetime.now(dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(pub)
         .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
         .not_valid_after(now + dt.timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
         .add_extension(x509.KeyUsage(digital_signature=not ca, content_commitment=False, key_encipherment=False,
                                      data_encipherment=False, key_agreement=False, key_cert_sign=ca, crl_sign=ca,
                                      encipher_only=False, decipher_only=False), critical=True)
         .add_extension(x509.SubjectKeyIdentifier.from_public_key(pub), critical=False)
         .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_pub), critical=False))
    if marker is not None:
        b = b.add_extension(x509.UnrecognizedExtension(marker, b"\x05\x00"), critical=False)
    return b.sign(signer, hashes.SHA256())


@dataclass
class Chain:
    root_der: bytes
    x5c: list[str]
    leaf_key: ec.EllipticCurvePrivateKey


def make_chain(*, leaf_marker=True) -> Chain:
    rk, ik, lk = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert(_name("Test Apple Root"), _name("Test Apple Root"), rk.public_key(), rk, ca=True)
    inter = _cert(_name("Test WWDR"), root.subject, ik.public_key(), rk, ca=True, marker=INTERMEDIATE_OID)
    leaf = _cert(_name("Test Leaf"), inter.subject, lk.public_key(), ik, ca=False, marker=LEAF_OID if leaf_marker else None)
    enc = lambda c: base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode()  # noqa: E731
    return Chain(root_der=root.public_bytes(serialization.Encoding.DER), x5c=[enc(leaf), enc(inter), enc(root)], leaf_key=lk)


def write_root(chain: Chain, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "TestRoot.cer").write_bytes(chain.root_der)
    return directory


def sign(chain: Chain, payload: dict) -> str:
    return jwt.encode(payload, chain.leaf_key, algorithm="ES256", headers={"x5c": chain.x5c})


def txn_payload(*, token, orig="1000", tid="1000", product="com.lingzhang.story.plus.monthly", bundle="com.lingzhang.story",
                env="Sandbox", purchase_ms=1_800_000_000_000, expires_ms=1_802_592_000_000, signed_ms=None, revoked_ms=None):
    p = {"originalTransactionId": orig, "transactionId": tid, "productId": product, "bundleId": bundle,
         "environment": env, "purchaseDate": purchase_ms, "originalPurchaseDate": purchase_ms, "expiresDate": expires_ms,
         "type": "Auto-Renewable Subscription", "signedDate": signed_ms or purchase_ms, "quantity": 1,
         "inAppOwnershipType": "PURCHASED"}
    if token:
        p["appAccountToken"] = token
    if revoked_ms:
        p["revocationDate"] = revoked_ms
        p["revocationReason"] = 0
    return p


def notification_payload(chain: Chain, *, ntype, subtype=None, uuid="11111111-1111-4111-8111-111111111111", txn=None,
                         renewal=None, env="Sandbox", bundle="com.lingzhang.story", signed_ms=1_800_000_000_000):
    data = {"environment": env, "bundleId": bundle, "appAppleId": 6826007175}
    if txn is not None:
        data["signedTransactionInfo"] = sign(chain, txn)
    if renewal is not None:
        data["signedRenewalInfo"] = sign(chain, renewal)
    p = {"notificationType": ntype, "notificationUUID": uuid, "data": data, "version": "2.0", "signedDate": signed_ms}
    if subtype:
        p["subtype"] = subtype
    return p
