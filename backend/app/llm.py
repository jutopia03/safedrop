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


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                         base_url=os.getenv("OPENAI_BASE_URL") or None,
                         timeout=40, max_retries=1)
    return _client


def complete_json(system: str, user: str, max_tokens: int = 3000) -> dict:
    """프롬프트를 보내고 JSON 객체 하나를 돌려받는다. 실패하면 LLMError."""
    from openai import APIError
    try:
        res = _get_client().chat.completions.create(
            model=model_name(),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_completion_tokens=max_tokens,
        )
    except APIError as e:
        raise LLMError(f"LLM 호출 실패: {getattr(e, 'status_code', '')} {getattr(e, 'message', e)}") from e
    choice = res.choices[0]
    content = choice.message.content or ""
    if not content and choice.finish_reason == "length":
        raise LLMError("출력 토큰 한도 부족(빈 답변)")
    m = re.search(r"\{.*\}", content, re.S)  # 앞뒤 설명이 붙어 와도 JSON 부분만 꺼낸다
    if not m:
        raise LLMError("JSON 형식 응답이 아님")
    try:
        return json.loads(m.group())
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 해석 실패: {e}") from e
