# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11", "numpy>=2"]
# ///
"""Render a computer-use screen recording into a captioned demo video.

Layout (1920x1080): header with model/elapsed/speed, the app window cropped from the
screen recording on the left, and a live "agent action log" panel on the right.
Time while the model is generating is fast-forwarded; tool execution plays at 1x.

Usage: uv run scripts/make_cu_video.py results/cu-calculator/video_meta.json
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS_OUT, FPS_SRC = 1920, 1080, 30, 15
SPEED_GEN, SPEED_TOOL, SPEED_IDLE = 6.0, 1.0, 3.0
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
SYMBOL_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"  # has ✓ ✗ glyphs
BG, PANEL, INK, MUTED, ACCENT, GOOD, BAD = "#0f1115", "#181b22", "#e8e8e8", "#8b93a3", "#76b900", "#4cc38a", "#ff6b6b"
LEFT = (30, 100, 1250, 1050)    # x0, y0, x1, y1 for the app view
RIGHT = (1280, 100, 1890, 1050)  # action log panel


def f(size):
    return ImageFont.truetype(FONT, size)


def wrap(text: str, font, width: int, max_lines: int) -> list[str]:
    lines, cur = [], ""
    for ch in text.replace("\n", " "):
        if font.getlength(cur + ch) > width:
            lines.append(cur)
            cur = ch.lstrip()
            if len(lines) == max_lines:
                lines[-1] = lines[-1][:-1] + "…"
                return lines
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def summarize_call(name: str, args: dict) -> str:
    if name == "act_ui":
        parts = []
        for a in args.get("actions", []):
            s = a.get("action", "?")
            if "ref" in a:
                s += f" {a['ref']}"
            if "x" in a:
                s += f" ({a['x']},{a['y']})"
            if "text" in a:
                s += f" 「{a['text']}」"
            if "key" in a or "keys" in a:
                s += f" {a.get('key') or a.get('keys')}"
            if "value" in a:
                s += f" ={a['value']}"
            parts.append(s)
        return "act_ui：" + "；".join(parts)
    if name == "search_ui":
        q = args.get("text") or args.get("role") or args.get("capability")
        return f"search_ui：找「{q}」"
    if name == "observe_ui":
        return "observe_ui：截圖 + 讀取 UI 結構" + (f" {args['root']}" if args.get("root") else "")
    if name == "launch_browser":
        return f"launch_browser：{args.get('url', '')}"
    if name == "navigate_browser":
        return f"navigate_browser：{args.get('url', '')}"
    if name == "find_roots":
        return "find_roots：列出視窗"
    if name in ("inspect_ui", "expand_ui"):
        return f"{name}：{args.get('ref', '')}"
    if name == "wait_for":
        return "wait_for：" + json.dumps(args, ensure_ascii=False)[:60]
    return f"{name}：" + json.dumps(args, ensure_ascii=False)[:60]


def load_timeline(jsonl: Path):
    """Return (log entries, speed segments, final answer)."""
    entries, segs, final = [], [], ""
    gen_start = None
    for line in jsonl.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        ev = json.loads(line)
        t, typ = ev["_t"], ev.get("type")
        if typ == "message_start" and ev["message"].get("role") == "assistant":
            gen_start = t
        elif typ == "message_end" and ev["message"].get("role") == "assistant":
            if gen_start:
                segs.append((gen_start, t, "gen"))
            for b in ev["message"]["content"]:
                if b["type"] == "thinking" and b.get("thinking", "").strip():
                    entries.append({"t": t, "kind": "think", "text": b["thinking"].strip()})
                elif b["type"] == "text" and b["text"].strip():
                    final = b["text"].strip()
            gen_start = None
        elif typ == "tool_execution_start":
            entries.append({"t": t, "kind": "call", "id": ev["toolCallId"], "text": summarize_call(ev["toolName"], ev.get("args") or {})})
            segs.append((t, None, "tool"))
        elif typ == "tool_execution_end":
            for s_i in range(len(segs) - 1, -1, -1):
                if segs[s_i][2] == "tool" and segs[s_i][1] is None:
                    segs[s_i] = (segs[s_i][0], t + 1.0, "tool")
                    break
            res = ev.get("result") or {}
            txt = " ".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text").strip()
            for e in reversed(entries):
                if e.get("id") == ev["toolCallId"]:
                    e["done"] = t
                    e["ok"] = not ev.get("isError")
                    e["result"] = txt.splitlines()[0][:80] if txt else ""
                    break
    return entries, [s for s in segs if s[1]], final


def speed_at(t: float, segs) -> float:
    sp = SPEED_IDLE
    for a, b, kind in segs:
        if a <= t < b:
            if kind == "tool":
                return SPEED_TOOL
            sp = SPEED_GEN
    return sp


def draw_frame(view: Image.Image, t: float, meta, entries, final: str, show_final: bool, speed: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # header
    d.text((30, 22), "NVIDIA Nemotron 3.5 Super VL 120B-A12B · NVFP4 @ DGX Spark", font=f(30), fill=INK)
    d.text((30, 62), "pi + pi-computer-use · 由模型自行看畫面、操作 macOS", font=f(20), fill=MUTED)
    el = max(0, t - meta["t0"])
    d.text((W - 30, 26), f"實際經過 {int(el // 60):02d}:{int(el % 60):02d}", font=f(28), fill=INK, anchor="ra")
    d.text((W - 30, 64), f"播放速度 {speed:g}×", font=f(20), fill=ACCENT if speed > 1 else MUTED, anchor="ra")
    # app view
    x0, y0, x1, y1 = LEFT
    img.paste(view, (x0 + (x1 - x0 - view.width) // 2, y0 + (y1 - y0 - view.height) // 2))
    # action log panel
    px0, py0, px1, py1 = RIGHT
    d.rounded_rectangle(RIGHT, 16, fill=PANEL)
    d.text((px0 + 20, py0 + 16), "Agent 動作紀錄", font=f(24), fill=INK)
    busy = next((e for e in entries if e["kind"] == "call" and e["t"] <= t < e.get("done", 1e18)), None)
    status = "● 完成" if show_final else (f"● 執行中：{busy['text'].split('：')[0]}" if busy else "● 模型思考中…")
    d.text((px1 - 20, py0 + 20), status, font=f(18), fill=ACCENT if busy or show_final else "#f0b429", anchor="ra")
    blocks = []
    for e in (e for e in entries if e["t"] <= t):
        if e["kind"] == "think":
            blocks.append(("想", wrap(e["text"], f(17), px1 - px0 - 70, 2), MUTED, None))
        else:
            mark = "…" if e.get("done", 1e18) > t else ("✓" if e.get("ok") else "✗")
            col = INK if mark == "…" else (GOOD if mark == "✓" else BAD)
            lines = wrap(e["text"], f(19), px1 - px0 - 70, 2)
            res = e.get("result") if e.get("done", 1e18) <= t else None
            blocks.append((mark, lines, col, res))
    # bottom-anchored list so the newest step is always visible
    y = py1 - 20 - (300 if show_final else 0)
    for mark, lines, col, res in reversed(blocks):
        h = 26 * len(lines) + (24 if res else 0) + 12
        if y - h < py0 + 60:
            break
        y -= h
        d.text((px0 + 20, y), mark, font=f(20) if mark == "想" else ImageFont.truetype(SYMBOL_FONT, 20), fill=col)
        for i, ln in enumerate(lines):
            d.text((px0 + 52, y + i * 26), ln, font=f(19 if mark != "想" else 17), fill=col if mark != "想" else MUTED)
        if res:
            d.text((px0 + 52, y + 26 * len(lines)), "→ " + wrap(res, f(15), px1 - px0 - 90, 1)[0], font=f(15), fill=MUTED)
    if show_final:
        fy0 = py1 - 300
        d.rounded_rectangle((px0 + 12, fy0, px1 - 12, py1 - 12), 12, fill="#1f2a14", outline=ACCENT, width=2)
        d.text((px0 + 30, fy0 + 14), "最終回答", font=f(20), fill=ACCENT)
        for i, ln in enumerate(wrap(final, f(19), px1 - px0 - 70, 9)):
            d.text((px0 + 30, fy0 + 48 + i * 26), ln, font=f(19), fill=INK)
    return img


def main():
    meta = json.loads(Path(sys.argv[1]).read_text())
    entries, segs, final = load_timeline(Path(meta["jsonl"]))
    win = meta["window"]
    src = Path(meta["video"])
    sw, sh = map(int, subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
                                     capture_output=True, text=True).stdout.strip().split(","))
    # crop window + margin, clamp to screen; enforce a minimum size so tiny apps keep some context
    m = 40
    cw, ch = max(win["w"] + 2 * m, 700), max(win["h"] + 2 * m, 560)
    cx, cy = win["x"] + win["w"] / 2, win["y"] + win["h"] / 2
    cw, ch = min(cw, sw), min(ch, sh)
    x = int(min(max(cx - cw / 2, 0), sw - cw))
    y = int(min(max(cy - ch / 2, 0), sh - ch))
    lw, lh = LEFT[2] - LEFT[0], LEFT[3] - LEFT[1]
    s = min(lw / cw, lh / ch)
    vw, vh = int(cw * s) // 2 * 2, int(ch * s) // 2 * 2

    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-vf", f"crop={int(cw)}:{int(ch)}:{x}:{y},scale={vw}:{vh}:flags=lanczos",
                            "-fps_mode", "cfr", "-r", str(FPS_SRC), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    out_path = Path(sys.argv[1]).parent.parent / f"cu-{meta['name']}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS_OUT), "-i", "-",
                            "-c:v", "h264_videotoolbox", "-b:v", "10M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)],
                           stdin=subprocess.PIPE)
    t_end = max([e.get("done", e["t"]) for e in entries] + [meta["t0"]]) + 1.0
    frame_bytes = vw * vh * 3
    src_i, cur, t_out = 0, None, meta["t0"] - 0.5
    n_out = 0
    while t_out < t_end:
        need = int((t_out - meta["t_rec"]) * FPS_SRC)
        while src_i <= need:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                need = -1
                break
            cur = Image.frombuffer("RGB", (vw, vh), buf)
            src_i += 1
        if cur is None:
            t_out += 1 / FPS_SRC
            continue
        sp = speed_at(t_out, segs)
        enc.stdin.write(draw_frame(cur, t_out, meta, entries, final, False, sp).tobytes())
        n_out += 1
        t_out += sp / FPS_OUT
        if need == -1:
            break
    end_card = draw_frame(cur, t_end, meta, entries, final, True, 1.0).tobytes()
    for _ in range(FPS_OUT * 6):
        enc.stdin.write(end_card)
    enc.stdin.close()
    enc.wait()
    dec.kill()
    print(f"video: {out_path} ({(n_out + FPS_OUT * 6) / FPS_OUT:.0f}s)")


if __name__ == "__main__":
    main()
