"""SafeDrop 백엔드 진입점.

흐름: 로그인(auth) → 추출(extract) → 탐지(detect) → 수신자별 판정(policy) → 마스킹(mask)
      → 전송 허가 토큰(permit) → P2P 전송(신호 중계) 또는 서버 중계(transfer) → 감사 로그

보안 원칙
- '나'(발신자·수신자)는 항상 서버가 발급한 세션 토큰에서 꺼낸다. 클라이언트가 보낸 이름표를 믿지 않는다.
- 업로드 크기를 제한해 큰 파일 하나로 서버가 멈추지 않게 한다.
- 감사 로그·성능 측정(AI 크레딧 사용)은 정보보호 관리자만 볼 수 있다.
"""
import asyncio
import hashlib
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, llm, permit, transfer
from .detect import detect
from .explain import explain
from .extract import extract_text
from .mask import mask_text
from .policy import judge
from .sensitive import detect_sensitive

ROOT = Path(__file__).resolve().parents[2]  # 저장소 루트
DATA = ROOT / "data" / "company"
MAX_UPLOAD = 10 * 1024 * 1024               # 업로드 최대 10MB

app = FastAPI(title="SafeDrop")


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _people() -> dict[str, dict]:
    return {p["id"]: p for p in load_json("org.json")["people"]}


# ---------------- 인증 ----------------
def current_user(request: Request) -> dict:
    """Authorization: Bearer <세션 토큰> 에서 사용자를 꺼낸다. 없거나 위조면 401."""
    header = request.headers.get("authorization", "")
    uid = auth.read_session(header[7:] if header.lower().startswith("bearer ") else None)
    user = _people().get(uid) if uid else None
    if not user:
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if not user.get("admin"):
        raise HTTPException(403, "정보보호 관리자만 볼 수 있습니다")
    return user


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """본문이 너무 큰 요청은 읽기 전에 거절한다 (Content-Length 기준, 실제 크기는 각 API에서 한 번 더 확인)."""
    size = request.headers.get("content-length")
    if request.method in ("POST", "PUT") and size and size.isdigit() and int(size) > MAX_UPLOAD + 64 * 1024:
        return JSONResponse({"detail": f"파일이 너무 큽니다 (최대 {MAX_UPLOAD // 1024 // 1024}MB)"}, status_code=413)
    return await call_next(request)


def _check_size(data: bytes):
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_UPLOAD // 1024 // 1024}MB)")


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    ip = request.client.host if request.client else "?"
    if auth.too_many_fails(ip):
        raise HTTPException(429, "로그인 실패가 많습니다. 1분 뒤 다시 시도하세요")
    user = _people().get(body.get("uid"))
    if not user or not auth.check_password(ip, str(body.get("password", ""))):
        raise HTTPException(401, "직원 또는 비밀번호가 올바르지 않습니다")
    transfer.audit("login", sender=user["id"])
    return {"token": auth.issue_session(user["id"]), "user": user}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


# ---------------- 분석 공통 ----------------
# 같은 파일 내용(해시)의 AI 민감정보 판단 결과를 10분간 재사용 → '검사 → 전송'에서 AI를 두 번 부르지 않는다.
# (판단 결과만 보관하고 파일 원본은 보관하지 않는다. 판정은 매번 서버가 다시 계산한다.)
CACHE_TTL = 10 * 60
_sens_cache: dict[str, tuple[float, list, dict]] = {}
_judge_cache: dict[str, tuple[float, list, str]] = {}   # 검사 ID → (시각, 판정 결과, 검사한 사람)


def _purge(cache: dict):
    now = time.time()
    for k in [k for k, v in cache.items() if now - v[0] > CACHE_TTL]:
        del cache[k]


def _sensitive_cached(data: bytes, text: str):
    _purge(_sens_cache)
    key = hashlib.sha256(data).hexdigest()
    if key in _sens_cache:
        _, sens, info = _sens_cache[key]
        return list(sens), dict(info, cached=True)
    sens, info = detect_sensitive(text)
    if not info.get("error") and not info.get("injection"):   # 실패·공격 의심 결과는 캐시하지 않는다
        _sens_cache[key] = (time.time(), sens, info)
    return sens, info


async def _analyze(file: UploadFile, sender: dict, recipient_ids: str):
    """추출 → 탐지 → 수신자별 판정. /api/judge 와 /api/transfer 가 같은 로직을 쓴다."""
    if sender["external"]:
        raise HTTPException(403, "외부 수신자 계정은 파일을 보낼 수 없습니다")
    people = _people()
    rids = [r.strip() for r in recipient_ids.split(",") if r.strip()]
    if not rids or any(r not in people for r in rids):
        raise HTTPException(400, "수신자 id가 올바르지 않음")
    data = await file.read()
    _check_size(data)
    ex = extract_text(file.filename, data)
    entities, llm_info = [], {"llm": "off"}
    if ex.readable:
        entities = detect(ex.text)                       # v0: 정규식 + 검증
        # v1: 문맥형 민감정보 (LLM). 시간이 걸리는 호출이라 별도 스레드에서 실행해 서버 전체가 멈추지 않게 한다.
        sens, llm_info = await run_in_threadpool(_sensitive_cached, data, ex.text)
        entities += sens
    return data, ex, entities, llm_info, judge(entities, ex.readable, sender["id"], rids)


# ---------------- 공개 API ----------------
@app.get("/api/health")
def health():
    org = load_json("org.json")
    rules = load_json("rules.json")
    return {"status": "ok", "people": len(org["people"]), "rule_categories": list(rules["rules"].keys()),
            "llm": llm.model_name() if llm.enabled() else "off (규칙 탐지만 동작)"}


@app.get("/api/people")
def people():
    """로그인 화면과 수신자 선택에 쓰는 가상 조직도 (비밀 정보 없음)."""
    return load_json("org.json")["people"]


@app.get("/api/pubkey")
def pubkey():
    """수신자 브라우저가 토큰 서명을 검증할 때 쓰는 서버 공개키."""
    return permit.public_jwk()


# ---------------- 로그인 필요 API ----------------
@app.post("/api/judge")
async def judge_file(file: UploadFile = File(...), recipient_ids: str = Form(...),
                     user: dict = Depends(current_user)):
    """수신자별 판정 결과 + (MASK 수신자용) 마스킹 사본 미리보기. 전송은 하지 않는다."""
    _, ex, entities, llm_info, decisions = await _analyze(file, user, recipient_ids)
    for d in decisions:
        if d["action"] == "MASK":
            d["masked_preview"] = mask_text(ex.text, entities, d["mask_categories"])[:2000]
    explain(decisions, use_llm=False)   # 우선 기본(템플릿) 설명만 붙여 바로 응답
    _purge(_judge_cache)
    jid = uuid.uuid4().hex[:12]
    _judge_cache[jid] = (time.time(), decisions, user["id"])
    return {"filename": file.filename, "readable": ex.readable, "reason": ex.reason, "judge_id": jid,
            "ai_explain": llm.enabled(), "entities": [e.to_dict() for e in entities], "llm": llm_info,
            "decisions": decisions}


@app.get("/api/explain/{jid}")
async def explain_later(jid: str, user: dict = Depends(current_user)):
    """검사 결과에 AI 설명(검색된 조항 근거 + 인용 검증)을 나중에 붙인다. 검사한 본인만 요청할 수 있다."""
    item = _judge_cache.get(jid)
    if not item or item[2] != user["id"]:
        raise HTTPException(404, "검사 결과가 없거나 만료됨 (다시 검사하세요)")
    decisions = item[1]
    t0 = time.time()
    await run_in_threadpool(explain, decisions)
    took = round(time.time() - t0, 1)
    for d in decisions:
        d["explanation"]["seconds"] = took        # 화면에 실제 걸린 시간 표시 (속도 근거)
        d["explanation"]["model"] = llm.explain_model()
    return {d["recipient"]["id"]: d["explanation"] for d in decisions}


@app.post("/api/transfer")
async def start_transfer(file: UploadFile = File(...), recipient_ids: str = Form(...),
                         user: dict = Depends(current_user)):
    """서버가 판정을 '다시' 수행하고(화면의 결과를 믿지 않음), 차단이 아닌 수신자마다 전송 허가 토큰을 발급한다."""
    data, ex, entities, _, decisions = await _analyze(file, user, recipient_ids)
    return transfer.prepare(file.filename, data, ex.text, entities, user["id"], decisions)


@app.get("/api/online")
def online(user: dict = Depends(current_user)):
    return transfer.signaling.online()


@app.put("/api/relay/{tid}/{rid}")
async def relay_put(tid: str, rid: str, request: Request, token: str, user: dict = Depends(current_user)):
    """P2P 연결 실패 시 대체 경로: 발신자가 올린 내용을 메모리에 잠시(최대 10분) 두고 수신자에게 알린다.
    서버가 발급한 토큰이고, 그 토큰의 발신자가 '로그인한 본인', 수신자·전송ID가 주소와 같을 때만 받는다."""
    claims = permit.verify(token)
    if not claims or claims.get("tid") != tid or claims.get("recipient") != rid or claims.get("sender") != user["id"]:
        raise HTTPException(403, "유효한 전송 허가 토큰이 아닙니다")
    data = await request.body()
    _check_size(data)
    meta = {"tid": tid, "sender": user["id"], "file": claims["file"], "token": token}
    transfer.relay_put(tid, rid, data, meta)
    transfer.audit("relayed", tid=tid, sender=user["id"], recipient=rid, file=claims["file"])
    await transfer.signaling.notify(rid, {"from": user["id"], "type": "relay", "data": meta})
    return {"ok": True}


@app.get("/api/relay/{tid}/{rid}")
def relay_get(tid: str, rid: str, user: dict = Depends(current_user)):
    """중계된 파일은 그 수신자 본인만 꺼낼 수 있다 (꺼내는 즉시 삭제)."""
    if user["id"] != rid:
        raise HTTPException(403, "본인에게 온 파일만 받을 수 있습니다")
    data = transfer.relay_take(tid, rid)
    if data is None:
        raise HTTPException(404, "중계 데이터가 없거나 만료됨")
    return Response(data, media_type="application/octet-stream")


@app.post("/api/receipt")
async def receipt(request: Request, user: dict = Depends(current_user)):
    """수신자 브라우저의 검증 결과(서명·해시·수신자·만료)를 감사 로그에 남긴다. 수신자는 로그인한 본인."""
    body = await request.json()
    transfer.audit("received", tid=body.get("tid"), recipient=user["id"],
                   verified=bool(body.get("verified")), via=body.get("via"), detail=body.get("detail", ""))
    return {"ok": True}


# ---------------- 관리자 전용 ----------------
_evals: dict[str, dict] = {}   # 측정 이름 → {status, started, finished, output}
_eval_lock = threading.Lock()


def _run_eval_job(name: str, script: str):
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], capture_output=True,
                           text=True, timeout=600, cwd=ROOT)
        out = r.stdout + (("\n[오류]\n" + r.stderr[-2000:]) if r.returncode else "")
    except Exception as e:  # 시간 초과 등
        out = f"[오류] {e}"
    _evals[name].update(status="done", finished=time.strftime("%Y-%m-%d %H:%M:%S"), output=out)


@app.get("/api/eval/{name}", response_class=PlainTextResponse)
def run_eval(name: str, rerun: int = 0, user: dict = Depends(admin_user)):
    """성능 측정을 서버에서 '백그라운드로' 실행한다 (AI를 여러 번 부르는 측정은 1~2분 걸려 요청이 끊기므로).
    처음 열면 측정을 시작하고, 다시 열면 진행 상황 또는 결과를 보여준다. ?rerun=1 이면 새로 측정.
    detect: 정규식 탐지 / retrieval: 조항 검색 / sensitive: AI 민감정보 판단 / explain: AI 설명 인용 검증"""
    scripts = {"detect": "eval_detect.py", "retrieval": "eval_retrieval.py",
               "sensitive": "eval_sensitive.py", "explain": "eval_explain.py"}
    if name not in scripts:
        raise HTTPException(404, f"가능한 측정: {', '.join(scripts)}")
    with _eval_lock:
        job = _evals.get(name)
        if job and job["status"] == "running":
            return f"측정 중입니다... (시작 {job['started']}, {int(time.time() - job['t'])}초 경과)\n1~2분 뒤 새로고침하세요."
        if job and not rerun:
            return f"[측정 시각 {job['finished']}]  다시 측정하려면 '다시 측정' 체크 후 버튼\n\n{job['output']}"
        _evals[name] = {"status": "running", "started": time.strftime("%H:%M:%S"), "t": time.time()}
        threading.Thread(target=_run_eval_job, args=(name, scripts[name]), daemon=True).start()
    return "측정을 시작했습니다. 1~2분 뒤 다시 확인하세요. (규칙 기반 측정은 몇 초면 끝납니다)"


@app.get("/api/audit")
def audit_log(limit: int = 100, user: dict = Depends(admin_user)):
    return transfer.read_audit(limit)


# ---------------- 신호 채널 ----------------
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    """WebRTC 연결 정보(offer/answer/ice)와 중계 알림을 전달하는 신호 채널.
    접속 후 첫 메시지로 세션 토큰을 보내야 하며, 그 토큰의 사용자로만 등록된다 (다른 사람 행세 불가)."""
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.close(code=4401)
        return
    uid = auth.read_session(first.get("token")) if first.get("type") == "auth" else None
    if not uid or uid not in _people():
        await websocket.close(code=4401)
        return
    await transfer.signaling.register(uid, websocket)
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
