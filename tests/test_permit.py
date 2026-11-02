"""전송 허가 토큰: 서버 서명이 공개키로 검증되고, 조작하면 검증에 실패해야 한다."""
import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from backend.app import permit


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _verify(token):
    payload, sig = token.split(".")
    jwk = permit.public_jwk()
    pub = ec.EllipticCurvePublicNumbers(int.from_bytes(_b64d(jwk["x"]), "big"),
                                        int.from_bytes(_b64d(jwk["y"]), "big"), ec.SECP256R1()).public_key()
    raw = _b64d(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    pub.verify(der, payload.encode(), ec.ECDSA(hashes.SHA256()))
    return json.loads(_b64d(payload))


def test_token_verifies_and_carries_claims():
    claims = _verify(permit.issue({"tid": "t1", "recipient": "u01", "sha256": "ab"}))
    assert claims["recipient"] == "u01" and claims["exp"] > 0


def test_tampered_token_fails():
    tok = permit.issue({"tid": "t1", "recipient": "u01", "sha256": "ab"})
    payload, sig = tok.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"tid": "t1", "recipient": "x01", "sha256": "ab"}).encode()).rstrip(b"=").decode()
    try:
        _verify(forged + "." + sig)
        assert False, "조작된 토큰이 통과하면 안 됨"
    except InvalidSignature:
        pass
