"""pytest 공통 설정: 저장소 루트를 import 경로에 넣고, 테스트 중에는 실제 LLM을 절대 부르지 않는다."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    from backend.app import llm
    monkeypatch.setattr(llm, "enabled", lambda: False)
