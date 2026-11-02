"""LLM 어댑터: 코디세이/OpenAI와 로컬 Ollama 양쪽에 맞게 요청을 만들고 응답을 해석하는지 (가짜 클라이언트)."""
from types import SimpleNamespace

from backend.app import llm


class FakeClient:
    def __init__(self, content):
        self.content, self.kwargs = content, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.kwargs = kw
        msg = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def _use(monkeypatch, base, content):
    fake = FakeClient(content)
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.delenv("LLM_TOKEN_PARAM", raising=False)
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    return fake


def test_codyssey_uses_max_completion_tokens(monkeypatch):
    fake = _use(monkeypatch, "https://copa.codyssey.kr/v1", '{"ok": 1}')
    assert llm.complete_json("s", "u") == {"ok": 1}
    assert "max_completion_tokens" in fake.kwargs and "max_tokens" not in fake.kwargs


def test_ollama_uses_max_tokens_and_strips_think(monkeypatch):
    fake = _use(monkeypatch, "http://localhost:11434/v1",
                '<think>{"results": "생각 중 예시"}</think>\n{"results": [1]}')
    assert llm.complete_json("s", "u") == {"results": [1]}
    assert "max_tokens" in fake.kwargs
