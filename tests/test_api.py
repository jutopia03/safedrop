"""B단계: 인증·권한·서버 보호 장치가 실제로 막는지 확인 (FastAPI TestClient, 네트워크·LLM 없음)."""
import pytest
from fastapi.testclient import TestClient

from backend.app import auth, main, transfer

PW = auth.demo_password()
DOC = "인사 발령 안내\n도윤슬 950312-2345678 연락처 010-9876-5432\n".encode()


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    auth._fails.clear()
    monkeypatch.setattr(transfer, "AUDIT", tmp_path / "audit.jsonl")
    yield
    auth._fails.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def login(client, uid):
    r = client.post("/api/login", json={"uid": uid, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_wrong_password_rejected(client):
    assert client.post("/api/login", json={"uid": "u05", "password": "nope"}).status_code == 401


def test_login_rate_limited(client):
    for _ in range(5):
        client.post("/api/login", json={"uid": "u05", "password": "nope"})
    # 맞는 비밀번호라도 잠시 막힌다
    assert client.post("/api/login", json={"uid": "u05", "password": PW}).status_code == 429


def test_no_token_401(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/judge", files={"file": ("a.txt", DOC)}, data={"recipient_ids": "u06"}).status_code == 401


def test_forged_session_401(client):
    good = login(client, "u05")["Authorization"].split(" ")[1]
    payload, sig = good.split(".")
    import base64, json
    fake = base64.urlsafe_b64encode(json.dumps({"uid": "u03", "exp": 9999999999}).encode()).rstrip(b"=").decode()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {fake}.{sig}"}).status_code == 401


def test_sender_comes_from_session(client):
    """폼에 sender_id=u01(인사팀장)을 끼워 넣어도 서버는 로그인한 u05를 발신자로 쓴다 (허가 토큰에 서명된 발신자로 확인)."""
    from backend.app import permit
    h = login(client, "u05")
    r = client.post("/api/transfer", headers=h, files={"file": ("a.txt", b"hello")},
                    data={"recipient_ids": "u06", "sender_id": "u01"})
    assert r.status_code == 200, r.text
    tok = r.json()["items"][0]["token"]
    assert permit.verify(tok)["sender"] == "u05"


def test_external_sender_forbidden(client):
    h = login(client, "x01")
    r = client.post("/api/judge", headers=h, files={"file": ("a.txt", DOC)}, data={"recipient_ids": "u05"})
    assert r.status_code == 403


def test_upload_too_large_413(client):
    h = login(client, "u05")
    big = b"a" * (10 * 1024 * 1024 + 200 * 1024)
    r = client.post("/api/judge", headers=h, files={"file": ("big.txt", big)}, data={"recipient_ids": "u06"})
    assert r.status_code == 413


def test_relay_put_requires_valid_own_token(client):
    h5 = login(client, "u05")
    r = client.post("/api/transfer", headers=h5, files={"file": ("a.txt", b"hello")}, data={"recipient_ids": "u06"})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["recipient"]["id"] == "u06")
    tid = r.json()["tid"]
    # 위조 토큰
    assert client.put(f"/api/relay/{tid}/u06?token=abc.def", headers=h5, content=b"x").status_code == 403
    # 남의 토큰으로 다른 사람이 올리기
    h7 = login(client, "u07")
    assert client.put(f"/api/relay/{tid}/u06?token={item['token']}", headers=h7, content=b"x").status_code == 403
    # 수신자 바꿔치기
    assert client.put(f"/api/relay/{tid}/u08?token={item['token']}", headers=h5, content=b"x").status_code == 403
    # 정상
    assert client.put(f"/api/relay/{tid}/u06?token={item['token']}", headers=h5, content=b"hello").status_code == 200
    # 다른 사람은 못 꺼냄, 수신자 본인은 꺼냄(1회)
    assert client.get(f"/api/relay/{tid}/u06", headers=h7).status_code == 403
    h6 = login(client, "u06")
    got = client.get(f"/api/relay/{tid}/u06", headers=h6)
    assert got.status_code == 200 and got.content == b"hello"
    assert client.get(f"/api/relay/{tid}/u06", headers=h6).status_code == 404


def test_admin_only_endpoints(client):
    h5 = login(client, "u05")
    assert client.get("/api/audit", headers=h5).status_code == 403
    assert client.get("/api/eval/detect", headers=h5).status_code == 403
    h3 = login(client, "u03")
    assert client.get("/api/audit", headers=h3).status_code == 200


def test_ws_requires_auth(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "bad.token"})
        with pytest.raises(Exception):
            ws.receive_json()
    h = login(client, "u06")["Authorization"].split(" ")[1]
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": h})
        # 연결 유지: 온라인 목록에 나타난다
        assert "u06" in client.get("/api/online", headers=login(client, "u06")).json()


def test_judge_returns_causes_but_does_not_cache_them(client):
    h = login(client, "u05")
    doc = "인사 발령 안내\n주민등록번호: 950312-2345678 연락처 010-9876-5432\n".encode()
    r = client.post("/api/judge", headers=h, files={"file": ("a.txt", doc)}, data={"recipient_ids": "x01"})
    d = r.json()["decisions"][0]
    assert d["action"] == "BLOCK" and any(c["hit"] == "950312-2345678" for c in d["causes"])
    cached = main._judge_cache[r.json()["judge_id"]][1][0]
    assert "causes" not in cached                                   # 원문 일부는 서버에 남기지 않음


def test_static_files_are_revalidated(client):
    """배포 후 예전 화면 코드가 남지 않도록 화면 파일은 매번 최신 여부를 확인하게 한다."""
    for path in ("/", "/app.js", "/style.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache"
