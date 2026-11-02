"""전송 허가 토큰 (S4).

서버가 판정을 마친 뒤, 차단이 아닌 수신자마다 토큰을 발급한다.
토큰 = base64url(내용 JSON) + "." + base64url(서명)
  내용: 전송 ID, 발신자, 수신자, 조치, 파일명, 보낼 파일의 SHA-256 해시, 만료 시각
  서명: 서버 개인키로 ECDSA P-256 서명 (브라우저 WebCrypto로 공개키 검증 가능)

수신자 브라우저는 ① 서명이 서버 것인지 ② 받은 파일의 해시가 토큰과 같은지 ③ 수신자가 나인지·만료 전인지
를 확인한다. 그래서 검사받지 않은 파일이나 바꿔치기한 파일은 받을 수 없다.

MVP 한계: 서명 키를 서버 시작 시 새로 만든다(재시작하면 이전 토큰은 무효). 운영에서는 키를 안전하게 보관해야 한다.
"""
import base64
import json
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

TOKEN_TTL_SEC = 10 * 60
_private_key = ec.generate_private_key(ec.SECP256R1())


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def public_jwk() -> dict:
    """브라우저(WebCrypto)가 가져다 쓸 수 있는 공개키 형식."""
    nums = _private_key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256",
            "x": _b64u(nums.x.to_bytes(32, "big")),
            "y": _b64u(nums.y.to_bytes(32, "big"))}


def issue(claims: dict) -> str:
    body = dict(claims, exp=int(time.time()) + TOKEN_TTL_SEC)
    payload = _b64u(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
    der = _private_key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    # WebCrypto는 DER이 아니라 r||s (각 32바이트) 형식을 기대한다
    return payload + "." + _b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def verify(token: str) -> dict | None:
    """서버가 발급한 토큰인지(서명) + 만료 전인지 확인하고 내용을 돌려준다. 서버 중계 업로드를 받을 때 쓴다."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    try:
        payload, sig = token.split(".")
        raw = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        _private_key.public_key().verify(der, payload.encode(), ec.ECDSA(hashes.SHA256()))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, InvalidSignature):
        return None
    return claims if claims.get("exp", 0) > time.time() else None
