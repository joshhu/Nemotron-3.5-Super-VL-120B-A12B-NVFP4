# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.60"]
# ///
"""Speed benchmark for the Nemotron 3.5 Super VL vLLM endpoint.

Measures, per scenario (streaming, one request at a time):
  TTFT          time to first streamed token (reasoning or content)
  prefill tok/s prompt_tokens / TTFT
  decode tok/s  (completion_tokens - 1) / (t_last - t_first)

Usage:
  uv run scripts/bench.py --base-url http://192.168.1.112:8000/v1 --label lilicorr
"""

import argparse
import base64
import json
import statistics
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
MODEL = "nemotron-3.5-super-vl"

FILLER = (
    "The DGX Spark is a compact desktop AI computer built around the GB10 Grace Blackwell "
    "superchip, which combines a 20-core Arm CPU with a Blackwell GPU and 128 GB of coherent "
    "unified LPDDR5x memory. "
)


def long_prompt(approx_tokens: int) -> str:
    # ~40 tokens per FILLER sentence; tag each chunk so prefix caching can't shortcut it across runs.
    n = approx_tokens // 40
    body = "".join(f"[{i}] {FILLER}" for i in range(n))
    return body + "\n\nIn one sentence, what is this text repeating?"


def image_content(path: Path, text: str):
    url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    return [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]


SCENARIOS = [
    {
        "name": "code (en, think off)",
        "messages": lambda: [{"role": "user", "content": "Write a complete, well-commented Python implementation of an LRU cache class with get/put, plus pytest unit tests."}],
        "max_tokens": 1024,
        "thinking": False,
    },
    {
        "name": "prose (zh-TW, think off)",
        "messages": lambda: [{"role": "user", "content": "請用繁體中文（台灣用語）寫一篇約 600 字的短文，介紹台灣夜市文化的歷史與特色。"}],
        "max_tokens": 1024,
        "thinking": False,
    },
    {
        "name": "reasoning (think on)",
        "messages": lambda: [{"role": "user", "content": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. A store sells 3 bats and 7 balls with a 10% discount on the whole order. What is the total? Show your work."}],
        "max_tokens": 4096,
        "thinking": True,
    },
    {
        "name": "prefill 8k ctx",
        "messages": lambda: [{"role": "user", "content": long_prompt(8000)}],
        "max_tokens": 64,
        "thinking": False,
    },
    {
        "name": "prefill 32k ctx",
        "messages": lambda: [{"role": "user", "content": long_prompt(32000)}],
        "max_tokens": 64,
        "thinking": False,
    },
    {
        "name": "image describe (think off)",
        "messages": lambda: [{"role": "user", "content": image_content(ROOT / "assets" / "chart.png", "Describe this chart in detail.")}],
        "max_tokens": 512,
        "thinking": False,
    },
]


def run_once(client: OpenAI, sc: dict, salt: int) -> dict:
    messages = sc["messages"]()
    # Unique prefix per run so prefix caching never serves a previous run's prefill.
    messages = [{"role": "system", "content": f"run-id {salt}-{time.time_ns()}"}] + messages
    t0 = time.perf_counter()
    t_first = t_last = None
    usage = None
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=sc["max_tokens"],
        temperature=1.0,
        top_p=0.95,
        stream=True,
        stream_options={"include_usage": True},
        extra_body={"chat_template_kwargs": {"enable_thinking": sc["thinking"]}},
    )
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        d = chunk.choices[0].delta
        piece = d.content or getattr(d, "reasoning_content", None) or getattr(d, "reasoning", None)
        if piece:
            now = time.perf_counter()
            if t_first is None:
                t_first = now
            t_last = now
    ttft = t_first - t0
    decode_s = max(t_last - t_first, 1e-9)
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "ttft_s": ttft,
        "prefill_tps": usage.prompt_tokens / ttft,
        "decode_tps": (usage.completion_tokens - 1) / decode_s,
        "total_s": t_last - t0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://192.168.1.112:8000/v1")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="default")
    args = ap.parse_args()

    client = OpenAI(base_url=args.base_url, api_key="EMPTY", timeout=600)
    print("warmup ...", flush=True)
    run_once(client, SCENARIOS[0] | {"max_tokens": 32}, 0)

    results = []
    for sc in SCENARIOS:
        runs = [run_once(client, sc, i) for i in range(args.runs)]
        med = lambda k: statistics.median(r[k] for r in runs)
        row = {
            "scenario": sc["name"],
            "prompt_tokens": int(med("prompt_tokens")),
            "completion_tokens": int(med("completion_tokens")),
            "ttft_s": med("ttft_s"),
            "prefill_tps": med("prefill_tps"),
            "decode_tps": med("decode_tps"),
            "runs": runs,
        }
        results.append(row)
        print(f"{row['scenario']:<28} prompt={row['prompt_tokens']:>6} gen={row['completion_tokens']:>5} "
              f"TTFT={row['ttft_s']:6.2f}s prefill={row['prefill_tps']:8.0f} tok/s decode={row['decode_tps']:6.1f} tok/s",
              flush=True)

    out = ROOT / "results" / f"bench-{args.label}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"label": args.label, "base_url": args.base_url, "results": results}, indent=2, ensure_ascii=False))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
