"""SafeDrop 백엔드 진입점.

흐름: 추출(extract) → 탐지(detect) → 수신자별 판정(policy) → 마스킹(mask)
      → 전송 허가 토큰(permit) → P2P 전송(신호 중계) 또는 서버 중계(transfer) → 감사 로그
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import llm, permit, transfer
from .detect import detect
from .explain import explain
from .extract import extract_text
from .mask import mask_text
from .policy import judge
from .sensitive import detect_sensitive

ROOT = Path(__file__).resolve().parents[2]  # 저장소 루트
DATA = ROOT / "data" / "company"

app = FastAPI(title="SafeDrop")


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _person_ids() -> set[str]:
    return {p["id"] for p in load_json("org.json")["people"]}


async def _analyze(file: UploadFile, sender_id: str, recipient_ids: str):
    """추출 → 탐지 → 수신자별 판정. /api/judge 와 /api/transfer 가 같은 로직을 쓴다."""
    ids = _person_ids()
    rids = [r.strip() for r in recipient_ids.split(",") if r.strip()]
    if sender_id not in ids or not rids or any(r not in ids for r in rids):
        raise HTTPException(400, "발신자 또는 수신자 id가 올바르지 않음")
    data = await file.read()
    ex = extract_text(file.filename, data)
    entities, llm_info = [], {"llm": "off"}
    if ex.readable:
        entities = detect(ex.text)                       # v0: 정규식 + 검증
        sens, llm_info = detect_sensitive(ex.text)       # v1: 문맥형 민감정보 (LLM)
        entities += sens
    return data, ex, entities, llm_info, judge(entities, ex.readable, sender_id, rids)


@app.get("/api/health")
def health():
    org = load_json("org.json")
    rules = load_json("rules.json")
    return {"status": "ok", "people": len(org["people"]), "rule_categories": list(rules["rules"].keys()),
            "llm": llm.model_name() if llm.enabled() else "off (규칙 탐지만 동작)"}


@app.get("/api/people")
def people():
    """화면에서 발신자·수신자를 고를 때 쓰는 가상 조직도."""
    return load_json("org.json")["people"]


@app.post("/api/scan")
async def scan(file: UploadFile = File(...)):
    """S2: 파일에서 텍스트를 뽑고 개인정보를 탐지한다. 원본은 메모리에서만 다루고 저장하지 않는다."""
    data = await file.read()
    ex = extract_text(file.filename, data)
    entities = detect(ex.text) if ex.readable else []
    return {"filename": file.filename, "readable": ex.readable, "reason": ex.reason,
            "entities": [e.to_dict() for e in entities]}


@app.post("/api/judge")
async def judge_file(file: UploadFile = File(...), sender_id: str = Form(...), recipient_ids: str = Form(...)):
    """S3: 수신자별 판정 결과 + (MASK 수신자용) 마스킹 사본 미리보기. 전송은 하지 않는다."""
    _, ex, entities, llm_info, decisions = await _analyze(file, sender_id, recipient_ids)
    for d in decisions:
        if d["action"] == "MASK":
            d["masked_preview"] = mask_text(ex.text, entities, d["mask_categories"])[:2000]
    explain(decisions)   # v2: 검색된 조항 근거로 AI 설명 생성 + 인용 검증 (실패 시 기본 설명)
    return {"filename": file.filename, "readable": ex.readable, "reason": ex.reason,
            "entities": [e.to_dict() for e in entities], "llm": llm_info, "decisions": decisions}


@app.post("/api/transfer")
async def start_transfer(file: UploadFile = File(...), sender_id: str = Form(...), recipient_ids: str = Form(...)):
    """S4: 서버가 판정을 '다시' 수행하고(화면의 결과를 믿지 않음), 차단이 아닌 수신자마다 전송 허가 토큰을 발급한다."""
    data, ex, entities, _, decisions = await _analyze(file, sender_id, recipient_ids)
    return transfer.prepare(file.filename, data, ex.text, entities, sender_id, decisions)


@app.get("/api/pubkey")
def pubkey():
    """수신자 브라우저가 토큰 서명을 검증할 때 쓰는 서버 공개키."""
    return permit.public_jwk()


@app.get("/api/online")
def online():
    return transfer.signaling.online()


@app.put("/api/relay/{tid}/{rid}")
async def relay_put(tid: str, rid: str, request: Request, sender: str, file: str, token: str):
    """P2P 연결 실패 시 대체 경로: 발신자가 올린 내용을 메모리에 잠시(최대 10분) 두고 수신자에게 알린다.
    내용이 바뀌었는지는 수신자가 토큰의 해시로 검증하므로 서버는 내용을 신뢰할 필요가 없다."""
    meta = {"tid": tid, "sender": sender, "file": file, "token": token}
    transfer.relay_put(tid, rid, await request.body(), meta)
    transfer.audit("relayed", tid=tid, sender=sender, recipient=rid, file=file)
    await transfer.signaling.notify(rid, {"from": sender, "type": "relay", "data": meta})
    return {"ok": True}


@app.get("/api/relay/{tid}/{rid}")
def relay_get(tid: str, rid: str):
    data = transfer.relay_take(tid, rid)  # 꺼내는 즉시 삭제
    if data is None:
        raise HTTPException(404, "중계 데이터가 없거나 만료됨")
    return Response(data, media_type="application/octet-stream")


@app.post("/api/receipt")
async def receipt(request: Request):
    """수신자 브라우저의 검증 결과(서명·해시·수신자·만료)를 감사 로그에 남긴다."""
    body = await request.json()
    transfer.audit("received", tid=body.get("tid"), recipient=body.get("recipient"),
                   verified=bool(body.get("verified")), via=body.get("via"), detail=body.get("detail", ""))
    return {"ok": True}


_last_eval = {"t": 0.0}


@app.get("/api/eval/{name}", response_class=PlainTextResponse)
def run_eval(name: str):
    """성능 측정 스크립트를 서버에서 실행하고 결과를 글자로 돌려준다 (배포 환경의 API 키로 측정하기 위함).
    detect: 정규식 탐지 / retrieval: 조항 검색 / sensitive: AI 민감정보 판단 / explain: AI 설명 인용 검증"""
    scripts = {"detect": "eval_detect.py", "retrieval": "eval_retrieval.py",
               "sensitive": "eval_sensitive.py", "explain": "eval_explain.py"}
    if name not in scripts:
        raise HTTPException(404, f"가능한 측정: {', '.join(scripts)}")
    if name in ("sensitive", "explain"):        # AI를 부르는 측정만 연속 호출 제한 (크레딧 보호)
        if time.time() - _last_eval["t"] < 30:
            raise HTTPException(429, "30초 후 다시 시도하세요")
        _last_eval["t"] = time.time()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / scripts[name])], capture_output=True,
                       text=True, timeout=300, cwd=ROOT)
    return r.stdout + (("\n[stderr]\n" + r.stderr) if r.returncode else "")


@app.get("/api/audit")
def audit_log(limit: int = 100):
    return transfer.read_audit(limit)


@app.websocket("/ws/{uid}")
async def ws(websocket: WebSocket, uid: str):
    """WebRTC 연결 정보(offer/answer/ice)와 중계 알림을 사용자 간에 전달하는 신호 채널."""
    await transfer.signaling.connect(uid, websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            delivered = await transfer.signaling.forward(uid, msg)
            if not delivered:
                await websocket.send_json({"type": "error", "data": f"{msg.get('to')} 접속 안 함"})
    except WebSocketDisconnect:
        transfer.signaling.disconnect(uid, websocket)


# 정적 화면(web/)은 API 라우트 뒤에 마운트한다.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
