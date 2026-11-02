"""시연용 로그인과 세션 (보안 보강).

- 가상 직원을 고르고 공통 시연 비밀번호(DEMO_PASSWORD)를 입력하면, 서버가 HMAC으로 서명한 세션 토큰을 발급한다.
- 이후 모든 요청의 '나'는 클라이언트가 보낸 값이 아니라 이 토큰에서 꺼낸 사용자다.
  (예전처럼 주소에 ?me=u01 을 붙여 다른 사람 행세를 할 수 없다)
- 토큰은 브라우저 탭마다 따로 보관(sessionStorage)하므로, 한 브라우저에서 탭별로 다른 직원으로 시연할 수 있다.
- 비밀번호 대입 공격을 막기 위해 같은 IP의 로그인 실패가 1분에 5회를 넘으면 잠시 막는다.

한계(MVP): 공통 비밀번호를 아는 사람은 누구로든 로그인할 수 있다. 실제 회사라면 사내 계정(SSO)과 연결한다.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SESSION_TTL_SEC = 8 * 60 * 60
_SECRET = (os.getenv("SESSION_SECRET") or secrets.token_hex(32)).encode()
_fails: dict[str, list[float]] = {}


def demo_password() -> str:
    return os.getenv("DEMO_PASSWORD") or "safedrop-demo"   # 배포 환경에서는 반드시 환경변수로 바꾼다


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def too_many_fails(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < 60]
    return len(_fails[ip]) >= 5


def check_password(ip: str, password: str) -> bool:
    ok = hmac.compare_digest(password.encode(), demo_password().encode())   # 시간 차이로 비밀번호를 추측하지 못하게
    if not ok:
        _fails.setdefault(ip, []).append(time.time())
    return ok


def issue_session(uid: str) -> str:
    payload = _b64(json.dumps({"uid": uid, "exp": int(time.time()) + SESSION_TTL_SEC}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session(token: str | None) -> str | None:
    """서명과 만료를 확인하고 사용자 id를 돌려준다. 잘못되면 None."""
    if not token or "." not in token:
        return None
    payload, sig = token.split(".", 1)
    good = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    return data["uid"] if data.get("exp", 0) > time.time() else None
