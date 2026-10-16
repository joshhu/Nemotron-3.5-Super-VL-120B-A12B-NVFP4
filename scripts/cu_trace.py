# /// script
# requires-python = ">=3.11"
# ///
"""Turn a `pi --mode json` computer-use run into a readable Markdown trace.

Screenshots returned by the computer-use tools are saved next to the trace as
results/<run>/step-NN.jpg so the run can be replayed visually.

Usage: uv run scripts/cu_trace.py results/cu-calculator.jsonl > results/cu-calculator.md
"""

import base64
import json
import sys
from pathlib import Path


def short(text: str, n: int = 600) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n] + f" …(+{len(text) - n} chars)"


def main():
    src = Path(sys.argv[1])
    shots = src.with_suffix("")
    shots.mkdir(exist_ok=True)
    out, step, turns = [f"# Computer-use trace: {src.stem}", ""], 0, 0
    tokens_in = tokens_out = 0
    t_start = t_end = None
    final_text = ""

    for line in src.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        ev = json.loads(line)
        typ = ev.get("type")
        if typ == "message_end":
            msg = ev["message"]
            ts = msg.get("timestamp")
            if ts:
                t_start = t_start or ts
                t_end = ts
            if msg.get("role") != "assistant":
                continue
            turns += 1
            u = msg.get("usage", {})
            tokens_in += u.get("input", 0)
            tokens_out += u.get("output", 0)
            out.append(f"## Turn {turns}  (in {u.get('input', 0)} / out {u.get('output', 0)} tok, stop={msg.get('stopReason')})")
            if msg.get("errorMessage"):
                out.append(f"**Error:** {msg['errorMessage']}")
            for block in msg["content"]:
                if block["type"] == "thinking" and block.get("thinking", "").strip():
                    out.append(f"<details><summary>思考</summary>\n\n```text\n{short(block['thinking'], 1500)}\n```\n</details>")
                elif block["type"] == "text" and block["text"].strip():
                    final_text = block["text"]
                    out.append(block["text"].strip())
                elif block["type"] == "toolCall":
                    out.append(f"**→ `{block['name']}`** `{json.dumps(block['arguments'], ensure_ascii=False)}`")
        elif typ == "tool_execution_end":
            res = ev.get("result") or {}
            texts, imgs = [], []
            for c in res.get("content", []):
                if c.get("type") == "text":
                    texts.append(c["text"])
                elif c.get("type") == "image":
                    step += 1
                    ext = "png" if c.get("mimeType") == "image/png" else "jpg"
                    p = shots / f"step-{step:02d}.{ext}"
                    p.write_bytes(base64.b64decode(c["data"]))
                    imgs.append(p)
            flag = " ❌" if ev.get("isError") else ""
            out.append(f"<details><summary>← {ev['toolName']}{flag} ({ev.get('durationMs', '?')} ms)</summary>\n\n```text\n{short(chr(10).join(texts), 2500)}\n```\n</details>")
            for p in imgs:
                out.append(f"![{p.name}]({p.parent.name}/{p.name})")
        out.append("")

    elapsed = (t_end - t_start) / 1000 if t_start and t_end else 0
    summary = [
        f"**Turns:** {turns} · **Screenshots:** {step} · **Tokens:** in {tokens_in:,} / out {tokens_out:,} · **Wall time:** {elapsed:.0f} s",
        "",
        "**Final answer:**",
        "",
        final_text.strip(),
        "",
    ]
    print("\n".join(out[:2] + summary + ["---", ""] + out[2:]))


if __name__ == "__main__":
    main()
