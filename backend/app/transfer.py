"""전송 준비·신호 중계·서버 중계·감사 로그 (S4).

- 파일 원본은 저장하지 않는다. 서버 중계(P2P 실패 시)만 메모리에 최대 10분 두고, 수신 즉시 삭제한다.
- 감사 로그에는 메타데이터(누가, 누구에게, 어떤 조치, 근거 조항, 해시)만 남긴다. (규정 8-1)
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

from fastapi import WebSocket

from . import permit
from .mask import mask_text

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "logs" / "audit.jsonl"
RELAY_TTL_SEC = 10 * 60


# ---------- 감사 로그 ----------
def audit(event: str, **fields):
    AUDIT.parent.mkdir(exist_ok=True)
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_audit(limit: int = 100) -> list[dict]:
    if not AUDIT.exists():
        return []
    lines = AUDIT.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(x) for x in reversed(lines)]


# ---------- 전송 준비: 수신자별 보낼 내용 + 토큰 ----------
def prepare(filename: str, data: bytes, text: str, entities: list, sender_id: str, decisions: list) -> dict:
    tid = uuid.uuid4().hex[:12]
    items = []
    for d in decisions:
        rid = d["recipient"]["id"]
        clauses = [r["clause"] for r in d["reasons"]]
        if d["action"] == "BLOCK":
            items.append({"recipient": d["recipient"], "action": "BLOCK"})
            audit("blocked", tid=tid, sender=sender_id, recipient=rid, file=filename, clauses=clauses)
            continue
        if d["action"] == "MASK":
            payload = mask_text(text, entities, d["mask_categories"]).encode("utf-8")
            name = filename.rsplit(".", 1)[0] + ".masked.txt"
        else:
            payload, name = data, filename
        sha = hashlib.sha256(payload).hexdigest()
        tok = permit.issue({"tid": tid, "sender": sender_id, "recipient": rid,
                           "action": d["action"], "file": name, "sha256": sha})
        item = {"recipient": d["recipient"], "action": d["action"], "file": name, "sha256": sha, "token": tok}
        if d["action"] == "MASK":
            # 마스킹 사본은 서버가 만들었으므로 발신자 브라우저에 돌려줘 P2P로 보내게 한다(서버에 남기지 않음)
            item["payload_text"] = payload.decode("utf-8")
        items.append(item)
        audit("approved", tid=tid, sender=sender_id, recipient=rid, file=name,
              action=d["action"], clauses=clauses, sha256=sha)
    return {"tid": tid, "items": items}


# ---------- 신호 중계 (WebRTC 연결 정보 전달) ----------
class Signaling:
    def __init__(self):
        self.peers: dict[str, WebSocket] = {}

    def online(self) -> list[str]:
        return list(self.peers)

    async def register(self, uid: str, ws: WebSocket):
        """인증을 마친(이미 accept 된) 연결을 사용자 id로 등록한다."""
        self.peers[uid] = ws
        # 접속하지 않은 동안 서버 중계로 도착한 파일이 있으면 알려준다
        for meta in relay_pending(uid):
            await ws.send_json({"from": meta["sender"], "type": "relay", "data": meta})

    async def notify(self, uid: str, msg: dict):
        if uid in self.peers:
            await self.peers[uid].send_json(msg)

    def disconnect(self, uid: str, ws: WebSocket):
        if self.peers.get(uid) is ws:
            del self.peers[uid]

    async def forward(self, sender: str, msg: dict) -> bool:
        """{to, type, data} 메시지를 대상에게 전달. 대상이 접속해 있지 않으면 False."""
        target = self.peers.get(msg.get("to"))
        if not target:
            return False
        await target.send_json({"from": sender, "type": msg.get("type"), "data": msg.get("data")})
        return True


signaling = Signaling()


# ---------- 서버 중계 (P2P 실패 시 대체 경로) ----------
_relay: dict[tuple[str, str], tuple[float, bytes, dict]] = {}


def relay_put(tid: str, rid: str, data: bytes, meta: dict):
    """meta: {tid, sender, file, token} - 수신자에게 보낼 알림 내용 (파일 내용 아님)"""
    _purge()
    _relay[(tid, rid)] = (time.time(), data, meta)


def relay_pending(rid: str) -> list[dict]:
    _purge()
    return [meta for (t, r), (_, _, meta) in _relay.items() if r == rid]


def relay_take(tid: str, rid: str) -> bytes | None:
    _purge()
    item = _relay.pop((tid, rid), None)  # 꺼내는 즉시 삭제
    return item[1] if item else None


def _purge():
    now = time.time()
    for k in [k for k, v in _relay.items() if now - v[0] > RELAY_TTL_SEC]:
        del _relay[k]
