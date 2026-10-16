# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.60"]
# ///
"""Run every showcase segment and record each one to results/videos/<segment>.mp4.

Terminal segments are recorded with asciinema (scripts/record_term.sh); the
computer-use segments are real screen recordings (scripts/computer_use_demo.py).

  uv run scripts/showcase.py                 # everything
  uv run scripts/showcase.py 04-pi-photo     # one segment
  uv run scripts/showcase.py --list
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from demo_multimodal import DEMOS  # noqa: E402  (shared prompts + ground truth)

ROOT = Path(__file__).resolve().parent.parent
PI = "pi -p --mode json --no-session --no-context-files --no-skills -ne --no-tools --model vllm-112-nemotron/nemotron-3.5-super-vl"


def pi_seg(name: str, title: str, prompt: str, thinking: str, image: str | None = None) -> dict:
    at = f"@assets/{image} " if image else ""
    cmd = f"{PI} --thinking {thinking} {at}{shlex.quote(prompt)} </dev/null | uv run -q scripts/pi_pretty.py --save results/{name}.md"
    show = f"pi --model vllm-112-nemotron/nemotron-3.5-super-vl --thinking {thinking} {at}\"{prompt[:60]}…\""
    return {"title": title, "cmd": cmd, "show": show}


def demo_seg(key: str, title: str) -> dict:
    d = DEMOS[key]
    return pi_seg(f"pi-{key}", title, d["prompt"], "high" if d["thinking"] else "off", d["file"])


SEGMENTS = {
    "01-pi-chat": pi_seg("pi-chat", "pi 純文字對話（不思考）",
                         "請用繁體中文（台灣用語），以 5 點條列說明 DGX Spark 這類桌上型 AI 電腦適合拿來做什麼，每點兩句話。", "off"),
    "02-pi-reasoning": pi_seg("pi-reasoning", "pi 推理模式（thinking on）",
                              "請用繁體中文回答：有 12 顆外觀相同的球，其中 1 顆重量不同（不知道較輕或較重）。只用天平秤 3 次，"
                              "如何找出那顆球並判斷它較輕或較重？請給出完整的分組策略。", "high"),
    "03-benchmark": {"title": "速度測試（TTFT / prefill / decode）",
                     "cmd": "uv run -q scripts/bench.py --label lilicorr",
                     "show": "uv run scripts/bench.py --label lilicorr", "size": "130x30"},
    "04-pi-photo": demo_seg("photo", "多模態：真實照片理解（士林夜市）"),
    "05-pi-receipt": demo_seg("receipt", "多模態：中文收據 OCR + 驗算找錯"),
    "06-pi-chart": demo_seg("chart", "多模態：圖表讀數與計算"),
    "07-pi-wireframe": demo_seg("wireframe", "多模態：手繪 wireframe → HTML"),
    "08-pi-geometry": demo_seg("geometry", "多模態：看圖解幾何題"),
    "09-video-events": {"title": "多模態：影片理解（事件順序 + 計數）",
                        "cmd": "uv run -q scripts/demo_multimodal.py video_events",
                        "show": "uv run scripts/demo_multimodal.py video_events   # OpenAI API, video_url"},
    "10-video-mrt": {"title": "多模態：真實影片理解（台北捷運進站）",
                     "cmd": "uv run -q scripts/demo_multimodal.py video_mrt",
                     "show": "uv run scripts/demo_multimodal.py video_mrt   # OpenAI API, video_url"},
    "11-cu-calculator": {"cu": "calculator"},
    "12-cu-order-form": {"cu": "order_form"},
}


def run(name: str):
    seg = SEGMENTS[name]
    print(f"\n######## {name} ########", flush=True)
    if "cu" in seg:
        subprocess.run(["uv", "run", "-q", "scripts/computer_use_demo.py", seg["cu"]], cwd=ROOT, check=True)
        src = ROOT / "results" / f"cu-{seg['cu']}.mp4"
        if src.exists():
            (ROOT / "results/videos").mkdir(parents=True, exist_ok=True)
            src.replace(ROOT / "results/videos" / f"{name}.mp4")
        return
    env = {"SHOW": seg["show"], "SIZE": seg.get("size", "120x34")}
    subprocess.run(["scripts/record_term.sh", name, seg["title"], seg["cmd"]], cwd=ROOT, check=True,
                   env={**__import__("os").environ, **env})
    if name == "07-pi-wireframe":
        render_wireframe()


def render_wireframe():
    """Extract the generated HTML and screenshot it with headless Chrome for a side-by-side comparison."""
    import re
    md = (ROOT / "results/pi-wireframe.md").read_text()
    m = re.search(r"```html\s*(.*?)```", md.split("## Answer", 1)[-1], re.S)
    if not m:
        print("!! no html block in wireframe answer")
        return
    html = ROOT / "results/pi-wireframe.html"
    html.write_text(m.group(1))
    png = ROOT / "results/pi-wireframe-render.png"
    subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu",
                    "--hide-scrollbars", f"--screenshot={png}", "--window-size=1280,860", html.as_uri()],
                   capture_output=True, timeout=60)
    print(f"rendered {png}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments", nargs="*", default=list(SEGMENTS))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        print("\n".join(SEGMENTS))
        return
    for s in args.segments:
        run(s)


if __name__ == "__main__":
    main()
