# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.60"]
# ///
"""Multimodal showcase for Nemotron 3.5 Super VL (image, OCR, chart, UI-to-code, geometry, video).

Each demo has a known ground truth (see `expect`) so answers can be checked, and
the full transcript + timing is written to results/demo-<name>.md.

Usage:
  uv run scripts/demo_multimodal.py                     # all demos
  uv run scripts/demo_multimodal.py receipt video_events
"""

import argparse
import base64
import mimetypes
import re
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
RESULTS = ROOT / "results"
MODEL = "nemotron-3.5-super-vl"
ZH = "請全程使用繁體中文（台灣用語）回答。"

DEMOS = {
    "photo": {
        "file": "shilin_night_market.jpg",
        "thinking": True,
        "prompt": ZH + "這張照片是在哪裡、什麼時候拍的？請列出你從畫面中讀到的所有文字（招牌、路牌、浮水印），"
                  "並推論排隊的人潮在買什麼、整體氛圍如何。最後說明你是根據哪些線索判斷的。",
        "expect": "台北士林夜市一帶（大西路 DaXi Rd. 路牌、士林伯豆花、Birkenstock）；2024.03.12 21:41；排隊在買燒烤（杏鮑菇）",
    },
    "receipt": {
        "file": "receipt_zh.png",
        "thinking": True,
        "prompt": ZH + "請把這張收據轉成 JSON（店名、地址、電話、時間、品項陣列[name, qty, amount]、合計、找零），"
                  "接著逐項驗算金額，告訴我收據上的合計有沒有算錯；若有錯，正確合計與正確找零應該是多少？",
        "expect": "品項加總 90+40+70+55+70 = 325，收據印 345 → 多收 20 元；付 500 元時正確找零 175（收據印 155）",
    },
    "chart": {
        "file": "chart.png",
        "thinking": True,
        "prompt": ZH + "請把圖表中所有數據整理成 Markdown 表格（季度、Cloud、Edge、營業利益率）。"
                  "然後計算：(1) 2025 全年 Cloud 營收相較 2024 全年的成長率；(2) 哪一季 Edge 營收出現季減？(3) 營業利益率最高的是哪一季？",
        "expect": "Cloud 2024=198、2025=288 → +45.5%；Edge 季減：Q2'24 (30→29)、Q1'25 (35→34)、Q4'25 (41→39)；利益率最高 Q4'25 26.1%",
    },
    "wireframe": {
        "file": "wireframe.png",
        "thinking": False,
        "prompt": "Convert this hand-drawn wireframe into a single self-contained HTML file with modern CSS (no external assets). "
                  "Match the layout faithfully: top nav, left sidebar, task list with checkboxes and tags, and the two cards at the bottom. "
                  "Output only the HTML in one ```html code block.",
        "expect": "版面還原：TaskFlow 導覽列、左側選單、3 筆任務（Review PR #42 / Write release notes / 1:1 with Mei）與標籤、Weekly progress 長條圖卡、Stats 卡",
        "save_html": True,
    },
    "geometry": {
        "file": "geometry.png",
        "thinking": True,
        "prompt": ZH + "根據圖中的直角三角形與標示，請求出：(1) BC 長度；(2) AD 長度；(3) CE 長度；(4) 三角形 CEB 的面積。請寫出推導過程，最後用一行列出四個答案。",
        "expect": "BC = √208 = 4√13 ≈ 14.42；AD = 2√13 ≈ 7.21；CE = √73 ≈ 8.54；△CEB 面積 = ½·9·8 = 36",
    },
    "video_events": {
        "file": "video_events.mp4",
        "thinking": True,
        "prompt": ZH + "請依時間順序描述這段影片中發生的每一個事件（物體、顏色、動作），並回答：影片最後畫面上總共有幾顆星星？",
        "expect": "紅球由左滾到右 → 藍色方塊從天而降落地 → 綠色三角形在中央旋轉 → 黃色星星逐一出現，最後共 5 顆",
    },
    "video_mrt": {
        "file": "mrt_zhishan.mp4",
        "thinking": False,
        "prompt": ZH + "請描述這段影片的內容與事件順序：這是什麼交通工具、在什麼樣的場所、發生了什麼事？請盡量指出畫面中的細節。",
        "expect": "台北捷運淡水線列車進站（2007-08-03 芝山站，高架月台），以畫面細節為準",
    },
}


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def run_demo(client: OpenAI, name: str, demo: dict) -> dict:
    path = ASSETS / demo["file"]
    media_type = "video_url" if path.suffix == ".mp4" else "image_url"
    content = [{"type": "text", "text": demo["prompt"]}, {"type": media_type, media_type: {"url": data_url(path)}}]

    t0 = time.perf_counter()
    t_first = None
    reasoning, answer, usage = [], [], None
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=16384,
        temperature=1.0,
        top_p=0.95,
        stream=True,
        stream_options={"include_usage": True},
        extra_body={"chat_template_kwargs": {"enable_thinking": demo["thinking"]}},
    )
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        d = chunk.choices[0].delta
        r = getattr(d, "reasoning_content", None) or getattr(d, "reasoning", None)
        if (r or d.content) and t_first is None:
            t_first = time.perf_counter()
        if r:
            reasoning.append(r)
        if d.content:
            answer.append(d.content)
            print(d.content, end="", flush=True)
    t_end = time.perf_counter()
    print()

    stats = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "ttft_s": round(t_first - t0, 2),
        "total_s": round(t_end - t0, 2),
        "decode_tps": round((usage.completion_tokens - 1) / max(t_end - t_first, 1e-9), 1),
    }
    answer_text = "".join(answer)
    md = [
        f"# Demo: {name}",
        f"![{demo['file']}](../assets/{demo['file']})" if media_type == "image_url" else f"Video: `assets/{demo['file']}`",
        f"**Thinking:** {'on' if demo['thinking'] else 'off'}  ",
        f"**Stats:** prompt {stats['prompt_tokens']} tok · output {stats['completion_tokens']} tok · "
        f"TTFT {stats['ttft_s']} s · total {stats['total_s']} s · decode {stats['decode_tps']} tok/s",
        "## Prompt", demo["prompt"],
        "## Expected (ground truth)", demo["expect"],
    ]
    if reasoning:
        md += ["## Reasoning", "<details><summary>展開思考過程</summary>\n\n```text\n" + "".join(reasoning).strip() + "\n```\n</details>"]
    md += ["## Answer", answer_text]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"demo-{name}.md").write_text("\n\n".join(md) + "\n")
    if demo.get("save_html"):
        m = re.search(r"```html\s*(.*?)```", answer_text, re.S)
        if m:
            (RESULTS / f"demo-{name}.html").write_text(m.group(1))
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demos", nargs="*", default=list(DEMOS))
    ap.add_argument("--base-url", default="http://192.168.1.112:8000/v1")
    args = ap.parse_args()
    client = OpenAI(base_url=args.base_url, api_key="EMPTY", timeout=1800)
    for name in args.demos:
        print(f"\n===== {name} =====", flush=True)
        stats = run_demo(client, name, DEMOS[name])
        print(f"[{name}] {stats}", flush=True)


if __name__ == "__main__":
    main()
