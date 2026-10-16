# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11", "matplotlib>=3.9", "numpy>=2"]
# ///
"""Generate synthetic test assets with known ground truth for the multimodal demo.

  assets/chart.png         grouped bar + line chart with exact values
  assets/receipt_zh.png    Traditional Chinese receipt whose printed total is deliberately wrong
  assets/wireframe.png     hand-drawn-style UI wireframe (screenshot -> HTML)
  assets/geometry.png      geometry problem drawn as a figure
  assets/video_events.mp4  20 s synthetic clip with an ordered sequence of events
"""

import math
import random
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CJK_FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
LATIN_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def font(size, cjk=True):
    return ImageFont.truetype(CJK_FONT if cjk else LATIN_FONT, size)


def make_chart():
    quarters = ["Q1'24", "Q2'24", "Q3'24", "Q4'24", "Q1'25", "Q2'25", "Q3'25", "Q4'25"]
    cloud = [42, 47, 51, 58, 63, 70, 74, 81]
    edge = [30, 29, 33, 35, 34, 38, 41, 39]
    margin = [18.5, 19.2, 21.0, 22.4, 21.8, 23.5, 24.9, 26.1]
    x = np.arange(len(quarters))
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=130)
    ax.bar(x - 0.2, cloud, 0.4, label="Cloud revenue ($M)", color="#4C78A8")
    ax.bar(x + 0.2, edge, 0.4, label="Edge devices revenue ($M)", color="#F58518")
    for i, (c, e) in enumerate(zip(cloud, edge)):
        ax.text(i - 0.2, c + 1, str(c), ha="center", fontsize=8)
        ax.text(i + 0.2, e + 1, str(e), ha="center", fontsize=8)
    ax.set_xticks(x, quarters)
    ax.set_ylabel("Revenue ($M)")
    ax.set_ylim(0, 95)
    ax2 = ax.twinx()
    ax2.plot(x, margin, "o-", color="#54A24B", label="Operating margin (%)")
    for i, m in enumerate(margin):
        ax2.annotate(f"{m}%", (i, m), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8, color="#2E6B2E")
    ax2.set_ylabel("Operating margin (%)")
    ax2.set_ylim(10, 30)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    ax.set_title("Acme Robotics — Quarterly Revenue by Segment, 2024–2025")
    fig.tight_layout()
    fig.savefig(OUT / "chart.png")
    plt.close(fig)


def make_receipt():
    items = [("蛋餅（加起司）", 2, 45), ("蘿蔔糕", 1, 40), ("大冰奶", 2, 35), ("鮪魚三明治", 1, 55), ("鐵板麵（黑胡椒）", 1, 70)]
    correct = sum(q * p for _, q, p in items)  # 370
    printed_total = 345  # deliberate error (correct sum is 325) for the model to catch
    W, H = 620, 900
    img = Image.new("RGB", (W, H), "#FBFAF5")
    d = ImageDraw.Draw(img)
    y = 40
    d.text((W // 2, y), "美而香早餐店", font=font(40), fill="black", anchor="mt"); y += 60
    d.text((W // 2, y), "新北市板橋區文化路一段 123 號", font=font(22), fill="#333", anchor="mt"); y += 34
    d.text((W // 2, y), "電話：(02) 2961-0000", font=font(22), fill="#333", anchor="mt"); y += 34
    d.text((W // 2, y), "2026/10/16  07:42   桌號 5", font=font(22), fill="#333", anchor="mt"); y += 50
    d.line((40, y, W - 40, y), fill="black", width=2); y += 20
    d.text((50, y), "品項", font=font(26), fill="black")
    d.text((380, y), "數量", font=font(26), fill="black")
    d.text((W - 50, y), "金額", font=font(26), fill="black", anchor="ra"); y += 44
    for name, q, p in items:
        d.text((50, y), name, font=font(26), fill="black")
        d.text((400, y), f"x{q}", font=font(26), fill="black")
        d.text((W - 50, y), f"{q * p}", font=font(26), fill="black", anchor="ra")
        y += 46
    y += 10
    d.line((40, y, W - 40, y), fill="black", width=2); y += 24
    d.text((50, y), "合計", font=font(32), fill="black")
    d.text((W - 50, y), f"NT$ {printed_total}", font=font(32), fill="black", anchor="ra"); y += 56
    d.text((50, y), "付款方式：現金   找零：NT$ 155", font=font(24), fill="#333"); y += 60
    d.text((W // 2, y), "謝謝光臨，祝您有美好的一天！", font=font(24), fill="#333", anchor="mt")
    # slight rotation + noise to make it look photographed
    img = img.rotate(2.2, expand=True, fillcolor="#D9D4C7")
    arr = np.asarray(img).astype(np.int16)
    arr += np.random.default_rng(0).integers(-12, 12, arr.shape, dtype=np.int16)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(OUT / "receipt_zh.png")
    return correct, printed_total


def wobbly_line(d, p1, p2, rng, width=3):
    (x1, y1), (x2, y2) = p1, p2
    n = 12
    pts = [(x1 + (x2 - x1) * t / n + rng.uniform(-1.5, 1.5), y1 + (y2 - y1) * t / n + rng.uniform(-1.5, 1.5)) for t in range(n + 1)]
    d.line(pts, fill="#222", width=width, joint="curve")


def wobbly_rect(d, box, rng, width=3):
    x1, y1, x2, y2 = box
    for a, b in [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]:
        wobbly_line(d, a, b, rng, width)


def make_wireframe():
    rng = random.Random(1)
    W, H = 1000, 700
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    f = lambda s: font(s, cjk=False)
    wobbly_rect(d, (20, 20, W - 20, 90), rng)  # nav bar
    d.text((45, 40), "TaskFlow", font=f(30), fill="#222")
    for i, t in enumerate(["Dashboard", "Projects", "Team"]):
        d.text((520 + i * 140, 45), t, font=f(22), fill="#222")
    d.ellipse((W - 80, 33, W - 40, 73), outline="#222", width=3)
    wobbly_rect(d, (20, 110, 240, H - 20), rng)  # sidebar
    for i, t in enumerate(["+ New task", "Inbox (4)", "Today", "Upcoming", "Done"]):
        d.text((40, 135 + i * 50), t, font=f(22), fill="#222")
    d.text((270, 115), "Today's tasks", font=f(32), fill="#222")
    for i, (task, tag) in enumerate([("Review PR #42", "urgent"), ("Write release notes", "docs"), ("1:1 with Mei", "meeting")]):
        y = 175 + i * 90
        wobbly_rect(d, (270, y, W - 40, y + 70), rng)
        wobbly_rect(d, (290, y + 22, 316, y + 48), rng, 2)  # checkbox
        d.text((335, y + 20), task, font=f(24), fill="#222")
        wobbly_rect(d, (W - 190, y + 18, W - 60, y + 52), rng, 2)
        d.text((W - 125, y + 35), tag, font=f(18), fill="#222", anchor="mm")
    wobbly_rect(d, (270, 460, 620, 670), rng)  # chart card
    d.text((290, 470), "Weekly progress", font=f(22), fill="#222")
    for i, h in enumerate([60, 100, 80, 130, 110]):
        wobbly_rect(d, (300 + i * 60, 650 - h, 340 + i * 60, 650), rng, 2)
    wobbly_rect(d, (650, 460, W - 40, 670), rng)  # stats card
    d.text((670, 470), "Stats", font=f(22), fill="#222")
    d.text((670, 520), "12 done", font=f(26), fill="#222")
    d.text((670, 565), "3 overdue", font=f(26), fill="#C00")
    d.text((670, 610), "87% on time", font=f(26), fill="#222")
    img.save(OUT / "wireframe.png")


def make_geometry():
    W, H = 900, 640
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f = lambda s: font(s, cjk=False)
    A, B, C = (120, 540), (720, 540), (120, 140)  # right angle at A: AB = 12, AC = 8 (50 px/unit)
    d.polygon([A, B, C], outline="black", width=4)
    d.rectangle((A[0], A[1] - 30, A[0] + 30, A[1]), outline="black", width=3)
    # D = midpoint of BC, segment AD
    D = ((B[0] + C[0]) / 2, (B[1] + C[1]) / 2)
    d.line([A, D], fill="#1f5fbf", width=3)
    # semicircle on AB (diameter AB) drawn below would leave canvas; mark point E on AB with AE = 3
    E = (A[0] + 3 * 50, A[1])
    d.line([C, E], fill="#c03020", width=3)
    for p, name, off in [(A, "A", (-35, 5)), (B, "B", (15, 5)), (C, "C", (-35, -30)), (D, "D", (10, -35)), (E, "E", (-10, 12))]:
        d.text((p[0] + off[0], p[1] + off[1]), name, font=f(32), fill="black")
    d.text((400, 560), "AB = 12", font=f(28), fill="black")
    d.text((15, 330), "AC = 8", font=f(28), fill="black")
    d.text((180, 560), "AE = 3", font=f(24), fill="#c03020")
    d.text((420, 40), "D is the midpoint of BC", font=f(26), fill="#1f5fbf")
    img.save(OUT / "geometry.png")


def make_video():
    W, H, FPS, SECS = 640, 360, 10, 20
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(OUT / "video_events.mp4")],
        stdin=subprocess.PIPE,
    )
    for i in range(FPS * SECS):
        t = i / FPS
        img = Image.new("RGB", (W, H), (235, 240, 248))
        d = ImageDraw.Draw(img)
        d.rectangle((0, H - 40, W, H), fill=(120, 170, 110))  # ground
        if t < 5:  # 1) red ball rolls left -> right
            x = 40 + (W - 80) * t / 5
            d.ellipse((x - 25, H - 90, x + 25, H - 40), fill=(220, 40, 40))
        elif t < 10:  # 2) blue box falls from the sky and lands
            y = min(-60 + (H - 40) * (t - 5) / 3, H - 100)
            d.rectangle((W / 2 - 30, y, W / 2 + 30, y + 60), fill=(40, 80, 220))
        elif t < 15:  # 3) green triangle spins in the centre
            a = (t - 10) * 2 * math.pi / 2.5
            cx, cy, r = W / 2, H / 2 - 20, 70
            pts = [(cx + r * math.cos(a + k * 2 * math.pi / 3), cy + r * math.sin(a + k * 2 * math.pi / 3)) for k in range(3)]
            d.polygon(pts, fill=(40, 170, 60))
        else:  # 4) yellow stars appear one per second (5 total by the end)
            n = min(int(t - 15) + 1, 5)
            for k in range(n):
                cx, cy = 90 + k * 115, 120
                pts = []
                for j in range(10):
                    rr = 40 if j % 2 == 0 else 17
                    ang = -math.pi / 2 + j * math.pi / 5
                    pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
                d.polygon(pts, fill=(245, 200, 30))
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    make_chart()
    correct, printed = make_receipt()
    make_wireframe()
    make_geometry()
    make_video()
    print(f"assets written to {OUT} (receipt correct total={correct}, printed={printed})")
