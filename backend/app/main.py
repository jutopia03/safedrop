"""SafeDrop 백엔드 진입점.

지금(S1)은 서버가 뜨는지와 가상 기업 데이터를 읽을 수 있는지만 확인한다.
탐지(S2), 판정(S3), 토큰·전송(S4)은 이후 단계에서 모듈로 추가한다.
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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


# 정적 화면(web/)은 API 라우트 뒤에 마운트한다.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
