"""로컬 LLM(Ollama) 성능·인프라 측정 — 팀원 실행용.

외부 API(코디세이)와 같은 측정 스크립트를 로컬 모델로 돌리고, GPU 메모리 최고 사용량·시간까지 기록해
docs/bench/ollama_<모델>.md 로 저장한다. 이 파일을 GitHub에 PR로 올리면 된다.
실행: python scripts/bench_local.py qwen3:8b
"""
import datetime
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class GpuWatch(threading.Thread):
    """1초마다 nvidia-smi로 GPU 메모리 사용량을 읽어 최고값을 기억한다."""
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.stop = 0, False

    def run(self):
        while not self.stop:
            out = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
            if out:
                self.peak = max(self.peak, int(out.splitlines()[0].strip() or 0))
            time.sleep(1)


def run_eval(script: str, env: dict) -> tuple[str, float]:
    t0 = time.time()
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=ROOT)
    return (p.stdout + p.stderr).strip(), time.time() - t0


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python scripts/bench_local.py <모델명>  (예: qwen3:8b)")
    model = sys.argv[1]
    env = dict(os.environ, OPENAI_API_KEY="ollama", OPENAI_BASE_URL=BASE, OPENAI_MODEL=model,
               EXPLAIN_MODEL=model, LLM_TIMEOUT="300", PYTHONIOENCODING="utf-8")
    gpu = sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]) or "(nvidia-smi 없음)"
    idle = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    size = next((l for l in sh(["ollama", "list"]).splitlines() if l.startswith(model)), "(ollama list에서 못 찾음)")
    print(f"GPU: {gpu}\n모델: {size}\n측정 시작 (모델에 따라 수 분 걸립니다)...")

    watch = GpuWatch(); watch.start()
    results = []
    for name, script in [("민감정보 판단 정확도", "eval_sensitive.py"), ("AI 설명 인용 검증", "eval_explain.py")]:
        print(f"\n▶ {name} ({script})")
        out, sec = run_eval(script, env)
        print(out[-1500:])
        results.append((name, script, out, sec))
    watch.stop = True; watch.join(timeout=3)

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    safe = model.replace(":", "_").replace("/", "_")
    path = ROOT / "docs" / "bench" / f"ollama_{safe}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# 로컬 LLM 측정: {model}", "",
             "| 항목 | 값 |", "|---|---|",
             f"| 측정 시각 | {stamp} |",
             f"| GPU | {gpu} |",
             f"| 측정 전 GPU 메모리 사용 | {idle or '?'} MiB |",
             f"| 측정 중 GPU 메모리 최고 | {watch.peak or '?'} MiB |",
             f"| 모델 (ollama list) | `{size}` |",
             f"| OS / Python | {platform.platform()} / {platform.python_version()} |", ""]
    for name, script, out, sec in results:
        lines += [f"## {name} (`{script}`, {sec:.1f}초)", "", "```", out[-3000:], "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 결과 저장: {path.relative_to(ROOT)}  → 이 파일을 GitHub에 PR로 올려 주세요")


if __name__ == "__main__":
    main()
