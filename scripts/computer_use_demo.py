# /// script
# requires-python = ">=3.11"
# dependencies = ["pyobjc-framework-Quartz>=11", "pyobjc-framework-Cocoa>=11"]
# ///
"""Computer-use demos: pi + @injaneity/pi-computer-use driven by Nemotron 3.5 Super VL on the DGX.

The agent operates THIS Mac (grant Accessibility + Screen Recording to
~/Applications/pi-computer-use.app). While it runs, every display is screen-recorded;
afterwards the display/rect of the app window is detected and make_cu_video.py renders
results/cu-<name>.mp4 with an agent-action side panel.

  uv run scripts/computer_use_demo.py                 # all demos
  uv run scripts/computer_use_demo.py calculator      # one demo
  uv run scripts/computer_use_demo.py --no-record order_form
"""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import AppKit
import Quartz

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
MODEL = os.environ.get("MODEL", "vllm-112-nemotron/nemotron-3.5-super-vl")
UI_TOOLS = "find_roots,observe_ui,search_ui,expand_ui,inspect_ui,act_ui,read_text,wait_for"
# launch_browser only accepts http(s) URLs, so the form is served from assets/ by a local http.server
FORM_PORT = 18765
FORM_URL = f"http://127.0.0.1:{FORM_PORT}/cu_order_form.html"

DEMOS = {
    "calculator": {
        "tools": UI_TOOLS,
        "setup": lambda: (subprocess.run(["open", "-a", "Calculator"]), time.sleep(1.5)),
        "pid": lambda: pgrep(["-x", "Calculator"]),
        "prompt": (
            "請使用 computer-use 工具操作 macOS 的「計算機」(Calculator) app：\n"
            "1. 先按 AC/C 清除，\n"
            "2. 用點按鈕的方式計算 1234 × 5678（不要用鍵盤輸入，不要心算），\n"
            "3. 按 = 之後，讀出計算機畫面上顯示的結果。\n"
            "最後用繁體中文回報你按了哪些按鈕，以及畫面上的結果。"
        ),
        "expect": "7,006,652",
    },
    "order_form": {
        "tools": UI_TOOLS + ",launch_browser,navigate_browser",
        "setup": lambda: serve_assets(),
        # the managed Chrome started by pi-computer-use carries --remote-debugging-port
        "pid": lambda: pgrep(["-f", "Google Chrome.app/Contents/MacOS/Google Chrome .*--remote-debugging-port"]),
        "prompt": (
            f"請使用 computer-use 工具開啟瀏覽器到 {FORM_URL} ，像真人一樣操作網頁表單完成訂餐（不可以執行 JavaScript）：\n"
            "- 訂購人姓名：王小明\n"
            "- 雞腿便當 2 個、紅茶 1 杯，其他品項維持 0\n"
            "- 取餐方式：外送\n"
            "然後按「送出訂單」。送出後讀取確認畫面，用繁體中文回報：訂單編號、運費、應付金額。"
        ),
        "expect": "訂單編號 A01944、運費 NT$50、應付 NT$315",
    },
}


def serve_assets():
    if subprocess.run(["curl", "-sf", "-o", "/dev/null", FORM_URL]).returncode != 0:
        subprocess.Popen(["python3", "-m", "http.server", str(FORM_PORT), "--bind", "127.0.0.1", "--directory", str(ROOT / "assets")],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(1)


def pgrep(args: list[str]) -> int | None:
    out = subprocess.run(["pgrep", *args], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def screens() -> list[dict]:
    """NSScreen frames converted to global top-left coordinates (same space as CGWindow bounds)."""
    ss = AppKit.NSScreen.screens()
    main_h = ss[0].frame().size.height
    res = []
    for i, s in enumerate(ss):
        f = s.frame()
        res.append({"index": i, "name": s.localizedName(), "x": f.origin.x, "y": main_h - (f.origin.y + f.size.height),
                    "w": f.size.width, "h": f.size.height, "scale": s.backingScaleFactor()})
    return res


def window_rect(pid: int | None) -> dict | None:
    if not pid:
        return None
    wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    best = None
    for w in wins:
        if w.get("kCGWindowOwnerPID") != pid or w.get("kCGWindowLayer") != 0:
            continue
        b = w["kCGWindowBounds"]
        if best is None or b["Width"] * b["Height"] > best["w"] * best["h"]:
            best = {"x": b["X"], "y": b["Y"], "w": b["Width"], "h": b["Height"]}
    return best


def locate(rect: dict) -> dict:
    cx, cy = rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2
    for s in screens():
        if s["x"] <= cx < s["x"] + s["w"] and s["y"] <= cy < s["y"] + s["h"]:
            return {"screen": s["index"], "x": rect["x"] - s["x"], "y": rect["y"] - s["y"], "w": rect["w"], "h": rect["h"]}
    return {"screen": 0, **rect}


def start_recording(name: str) -> list[tuple[subprocess.Popen, Path]]:
    # screencapture (ScreenCaptureKit) can record several displays at once; ffmpeg/avfoundation deadlocks
    # when more than one screen is captured concurrently. -D is 1-based in NSScreen order.
    procs = []
    for s in screens():
        out = RESULTS / f"cu-{name}" / f"screen{s['index']}.mov"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        p = subprocess.Popen(["screencapture", "-x", "-v", "-k", "-D", str(s["index"] + 1), str(out)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append((p, out))
    return procs


def stop_recording(procs):
    for p, _ in procs:
        p.send_signal(signal.SIGINT)
    for p, _ in procs:
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()


def run(name: str, record: bool, thinking: str):
    demo = DEMOS[name]
    RESULTS.mkdir(exist_ok=True)
    jsonl = RESULTS / f"cu-{name}.jsonl"
    print(f"===== {name} =====", flush=True)
    demo["setup"]()

    procs = start_recording(name) if record else []
    time.sleep(2)  # let avfoundation settle so the first frames are on disk
    t_rec = time.time() - 2

    cmd = ["pi", "-p", "--mode", "json", "--no-session", "--no-context-files", "--no-skills",
           "--model", MODEL, "--thinking", thinking, "--tools", demo["tools"], demo["prompt"]]
    t0 = time.time()
    rect = None
    with subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, cwd=ROOT) as pi, jsonl.open("w") as f:
        for raw in pi.stdout:  # LF-delimited JSONL; stamp each event with wall-clock time
            ev = json.loads(raw)
            ev["_t"] = time.time()
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            if ev.get("type") == "tool_execution_start":
                print(f"  {ev['_t'] - t0:6.1f}s  → {ev['toolName']} {json.dumps(ev.get('args', {}), ensure_ascii=False)[:120]}", flush=True)
            if ev.get("type") == "tool_execution_end":
                rect = window_rect(demo["pid"]()) or rect  # track the window while it is alive
    elapsed = time.time() - t0
    time.sleep(1.5)
    rect = window_rect(demo["pid"]()) or rect
    if procs:
        stop_recording(procs)

    trace_md = subprocess.run(["uv", "run", "-q", str(ROOT / "scripts/cu_trace.py"), str(jsonl)],
                              capture_output=True, text=True, check=True).stdout
    (RESULTS / f"cu-{name}.md").write_text(trace_md + f"\n**Expected:** {demo['expect']}\n")
    print(f"[{name}] agent finished in {elapsed:.0f}s; expected: {demo['expect']}")
    print("\n".join(trace_md.splitlines()[2:8]))

    if procs and rect:
        loc = locate(rect)
        meta = {"name": name, "t_rec": t_rec, "t0": t0, "window": loc, "model": MODEL, "thinking": thinking,
                "video": str(RESULTS / f"cu-{name}" / f"screen{loc['screen']}.mov"), "jsonl": str(jsonl)}
        meta_path = RESULTS / f"cu-{name}" / "video_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        subprocess.run(["uv", "run", "-q", str(ROOT / "scripts/make_cu_video.py"), str(meta_path)], check=True)
    elif procs:
        print("!! could not locate the app window; raw recordings kept in", RESULTS / f"cu-{name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demos", nargs="*", default=list(DEMOS))
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--thinking", default=os.environ.get("THINKING", "low"))
    args = ap.parse_args()
    for name in args.demos:
        run(name, not args.no_record, args.thinking)


if __name__ == "__main__":
    main()
