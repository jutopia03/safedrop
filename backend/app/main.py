"""SafeDrop 백엔드 진입점.

흐름: 추출(extract) → 탐지(detect) → 수신자별 판정(policy) → 마스킹(mask)
토큰·전송(S4)은 이후 단계에서 추가한다.
"""
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from .detect import detect
from .extract import extract_text
from .mask import mask_text
from .policy import judge

ROOT = Path(__file__).resolve().parents[2]  # 저장소 루트
DATA = ROOT / "data" / "company"

app = FastAPI(title="SafeDrop")


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    org = load_json("org.json")
    rules = load_json("rules.json")
    return {
        "status": "ok",
        "people": len(org["people"]),
        "rule_categories": list(rules["rules"].keys()),
    }


@app.get("/api/people")
def people():
    """화면에서 수신자를 고를 때 쓰는 가상 조직도."""
    return load_json("org.json")["people"]


@app.post("/api/scan")
async def scan(file: UploadFile = File(...)):
    """S2: 파일에서 텍스트를 뽑고 개인정보를 탐지한다. 원본은 메모리에서만 다루고 저장하지 않는다."""
    data = await file.read()
    ex = extract_text(file.filename, data)
    entities = detect(ex.text) if ex.readable else []
    return {
        "filename": file.filename,
        "readable": ex.readable,
        "reason": ex.reason,
        "entities": [e.to_dict() for e in entities],
    }


@app.post("/api/judge")
async def judge_file(
    file: UploadFile = File(...),
    sender_id: str = Form(...),
    recipient_ids: str = Form(..., description="쉼표로 구분한 수신자 id 목록"),
):
    """S3: 추출 → 탐지 → 수신자별 판정 → (MASK 수신자용) 마스킹 사본 미리보기."""
    people = {p["id"] for p in load_json("org.json")["people"]}
    rids = [r.strip() for r in recipient_ids.split(",") if r.strip()]
    if sender_id not in people or not rids or any(r not in people for r in rids):
        raise HTTPException(400, "발신자 또는 수신자 id가 올바르지 않음")

    data = await file.read()
    ex = extract_text(file.filename, data)
    entities = detect(ex.text) if ex.readable else []
    decisions = judge(entities, ex.readable, sender_id, rids)
    for d in decisions:
        if d["action"] == "MASK":
            d["masked_preview"] = mask_text(ex.text, entities, d["mask_categories"])[:2000]
    return {
        "filename": file.filename,
        "readable": ex.readable,
        "reason": ex.reason,
        "entities": [e.to_dict() for e in entities],
        "decisions": decisions,
    }


# 정적 화면(web/)은 API 라우트 뒤에 마운트한다.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
