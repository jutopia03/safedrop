"""LLM 호출 어댑터 (교체형 구조).

OpenAI 호환 API 하나로 여러 공급자를 '설정만 바꿔서' 쓴다.
- 코디세이 제공 키:  OPENAI_BASE_URL=https://copa.codyssey.kr/v1, OPENAI_MODEL=gpt-5-mini
- 로컬 GPU(온프레미스): Ollama 의 OpenAI 호환 주소 http://localhost:11434/v1, OPENAI_MODEL=<로컬 모델명>
- 공식 OpenAI: OPENAI_BASE_URL 비움

코디세이 중계 서버 주의점: reasoning_effort·temperature 를 보내지 않는다. GPT-5 계열은 숨은 추론 토큰을 쓰므로
출력 상한을 넉넉히(1500+) 둔다. 빈 답변 + finish_reason=length 는 한도 부족 오류로 처리한다.
"""
import json
import os
import re

try:  # 로컬 실행 시 .env 파일을 읽는다 (배포 환경에서는 플랫폼 환경변수 사용)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LLMError(Exception):
    pass


def enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5-mini")


def explain_model() -> str:
    """판정 설명 생성용 모델. 설명은 판정에 영향이 없으므로 더 빠른 모델로 따로 바꿔 시험할 수 있다."""
    return os.getenv("EXPLAIN_MODEL") or model_name()


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                         base_url=os.getenv("OPENAI_BASE_URL") or None,
                         timeout=float(os.getenv("LLM_TIMEOUT", "90")), max_retries=1)
    return _client


def _token_param() -> str:
    """출력 한도 파라미터 이름. OpenAI·코디세이는 max_completion_tokens, Ollama 등 로컬 서버는 max_tokens."""
    if os.getenv("LLM_TOKEN_PARAM"):
        return os.environ["LLM_TOKEN_PARAM"]
    base = os.getenv("OPENAI_BASE_URL") or ""
    return "max_completion_tokens" if (not base or "codyssey" in base or "openai.com" in base) else "max_tokens"


def complete_json(system: str, user: str, max_tokens: int = 4000, max_cap: int = 12000, model: str | None = None) -> dict:
    """프롬프트를 보내고 JSON 객체 하나를 돌려받는다. 실패하면 LLMError.
    추론 모델이 숨은 추론에 한도를 다 써서 빈 답변이 오면, 한도를 2배로 늘려 다시 시도한다(max_cap까지)."""
    from openai import APIError
    while True:
        try:
            res = _get_client().chat.completions.create(
                model=model or model_name(),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **{_token_param(): max_tokens},
            )
        except APIError as e:
            raise LLMError(f"LLM 호출 실패: {getattr(e, 'status_code', '')} {getattr(e, 'message', e)}") from e
        choice = res.choices[0]
        content = choice.message.content or ""
        if content or choice.finish_reason != "length":
            break
        if max_tokens * 2 > max_cap:
            raise LLMError(f"출력 토큰 한도 부족(빈 답변, 한도 {max_tokens})")
        max_tokens *= 2
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # 로컬 추론 모델(qwen3 등)의 생각 과정 제거
    m = re.search(r"\{.*\}", content, re.S)  # 앞뒤 설명이 붙어 와도 JSON 부분만 꺼낸다
    if not m:
        raise LLMError("JSON 형식 응답이 아님")
    try:
        return json.loads(m.group())
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 해석 실패: {e}") from e
