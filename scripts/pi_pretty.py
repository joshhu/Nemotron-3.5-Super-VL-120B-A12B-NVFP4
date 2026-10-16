# /// script
# requires-python = ">=3.11"
# ///
"""Pretty-print a live `pi -p --mode json` stream: thinking in grey, answer in white, then speed stats.

  pi -p --mode json --model vllm-112-nemotron/nemotron-3.5-super-vl @img.png "..." \
    | uv run scripts/pi_pretty.py --save results/pi-photo.md
"""

import argparse
import json
import sys
import time
from pathlib import Path

DIM, RESET, CYAN, GREEN, YELLOW, BOLD = "\033[38;5;245m", "\033[0m", "\033[36m", "\033[32m", "\033[33m", "\033[1m"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", help="write prompt/thinking/answer/stats as Markdown")
    args = ap.parse_args()

    t0 = time.time()
    t_first = None
    mode = None
    thinking, answer, prompt = [], [], ""
    usage = {}
    for raw in sys.stdin.buffer:
        ev = json.loads(raw)
        typ = ev.get("type")
        if typ == "message_end" and ev["message"].get("role") == "user":
            c = ev["message"]["content"]
            prompt = c if isinstance(c, str) else " ".join(b.get("text", "[image]") if b.get("type") == "text" else "[image]" for b in c)
        elif typ == "message_update":
            e = ev["assistantMessageEvent"]
            et = e.get("type")
            if et in ("thinking_delta", "text_delta") and t_first is None:
                t_first = time.time()
            if et == "thinking_start":
                sys.stdout.write(f"{YELLOW}▌思考中…{RESET}\n{DIM}")
                mode = "think"
            elif et == "thinking_delta":
                thinking.append(e["delta"])
                sys.stdout.write(e["delta"])
            elif et == "text_start":
                if mode == "think":
                    sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.write(f"{GREEN}▌回答{RESET}\n")
                mode = "text"
            elif et == "text_delta":
                answer.append(e["delta"])
                sys.stdout.write(e["delta"])
            elif et == "toolcall_end":
                tc = e["toolCall"]
                sys.stdout.write(f"\n{CYAN}→ {tc['name']} {json.dumps(tc['arguments'], ensure_ascii=False)[:150]}{RESET}\n")
            sys.stdout.flush()
        elif typ == "message_end" and ev["message"].get("role") == "assistant":
            usage = ev["message"].get("usage", {})
            if ev["message"].get("errorMessage"):
                sys.stdout.write(f"\n\033[31m[error] {ev['message']['errorMessage']}{RESET}\n")
    t_end = time.time()

    out_tok = usage.get("output", 0)
    ttft = (t_first or t_end) - t0
    gen = max(t_end - (t_first or t_end), 1e-9)
    stats = (f"輸入 {usage.get('input', 0):,} tok · 輸出 {out_tok:,} tok · 首字 {ttft:.2f}s · "
             f"總時間 {t_end - t0:.1f}s · 生成速度 {(out_tok - 1) / gen:.1f} tok/s")
    sys.stdout.write(f"{RESET}\n\n{BOLD}── {stats}{RESET}\n")

    if args.save:
        md = [f"## Prompt\n\n{prompt}"]
        if thinking:
            md.append("## Thinking\n\n<details><summary>展開</summary>\n\n```text\n" + "".join(thinking).strip() + "\n```\n</details>")
        md += ["## Answer\n\n" + "".join(answer).strip(), f"## Stats\n\n{stats}"]
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text("\n\n".join(md) + "\n")


if __name__ == "__main__":
    main()
