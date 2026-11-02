"""로컬 LLM(Ollama) 성능·인프라 측정 — 팀원 실행용.

외부 API(코디세이)와 같은 측정 스크립트를 로컬 모델로 돌리고, GPU 메모리 최고 사용량·시간까지 기록해
docs/bench/ollama_<모델>.md 로 저장한다. 이 파일을 GitHub에 PR로 올리면 된다.
- 측정 전에 메모리에 올라가 있던 모델을 모두 내려(ollama stop) GPU 메모리 수치가 섞이지 않게 한다
- 측정 중 `ollama ps`로 모델이 GPU에 다 올라갔는지(일부 CPU로 밀렸는지) 기록한다
- 모델의 원본 응답을 docs/bench/raw_<모델>.jsonl 에 남겨 실패 원인을 분석할 수 있게 한다
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


def unload_all():
    """메모리에 남아 있는 Ollama 모델을 모두 내린다 (Ollama는 기본으로 5분간 모델을 올려 둔다)."""
    for line in sh(["ollama", "ps"]).splitlines()[1:]:
        if line.strip():
            sh(["ollama", "stop", line.split()[0]])
    time.sleep(3)


def run_eval(script: str, env: dict) -> tuple[str, float]:
    t0 = time.time()
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=ROOT)
    return (p.stdout + p.stderr).strip(), time.time() - t0


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python scripts/bench_local.py <모델명>  (예: qwen3:8b)")
    model = sys.argv[1]
    safe = model.replace(":", "_").replace("/", "_")
    raw = ROOT / "docs" / "bench" / f"raw_{safe}.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("", encoding="utf-8")
    env = dict(os.environ, OPENAI_API_KEY="ollama", OPENAI_BASE_URL=BASE, OPENAI_MODEL=model,
               EXPLAIN_MODEL=model, LLM_TIMEOUT="300", PYTHONIOENCODING="utf-8", LLM_RAW_LOG=str(raw))
    unload_all()
    gpu = sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]) or "(nvidia-smi 없음)"
    idle = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    size = next((l for l in sh(["ollama", "list"]).splitlines() if l.startswith(model)), "(ollama list에서 못 찾음)")
    print(f"GPU: {gpu}\n모델: {size}\n측정 시작 (모델에 따라 수 분 걸립니다)...")

    watch = GpuWatch(); watch.start()
    results, placement = [], ""
    for name, script in [("민감정보 판단 정확도", "eval_sensitive.py"), ("AI 설명 인용 검증", "eval_explain.py")]:
        print(f"\n▶ {name} ({script})")
        out, sec = run_eval(script, env)
        print(out[-1500:])
        results.append((name, script, out, sec))
        placement = placement or next((l for l in sh(["ollama", "ps"]).splitlines()[1:] if l.startswith(model)), "")
    watch.stop = True; watch.join(timeout=3)
    unload_all()

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    path = ROOT / "docs" / "bench" / f"ollama_{safe}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# 로컬 LLM 측정: {model}", "",
             "| 항목 | 값 |", "|---|---|",
             f"| 측정 시각 | {stamp} |",
             f"| GPU | {gpu} |",
             f"| 측정 전 GPU 메모리 사용 | {idle or '?'} MiB |",
             f"| 측정 중 GPU 메모리 최고 | {watch.peak or '?'} MiB |",
             f"| 모델 사용 메모리 (최고 − 측정 전) | {(watch.peak - int(idle)) if idle.isdigit() and watch.peak else '?'} MiB |",
             f"| 모델 배치 (ollama ps) | `{placement or '(기록 못함)'}` |",
             f"| 모델 (ollama list) | `{size}` |",
             f"| OS / Python | {platform.platform()} / {platform.python_version()} |", ""]
    for name, script, out, sec in results:
        lines += [f"## {name} (`{script}`, {sec:.1f}초)", "", "```", out[-3000:], "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 결과 저장: {path.relative_to(ROOT)}, {raw.relative_to(ROOT)}  → 두 파일 모두 GitHub에 PR로 올려 주세요")


if __name__ == "__main__":
    main()
