# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11", "openai>=1.60"]
# ///
"""Prepend an "input image/video + prompt" card to the image-demo videos so viewers see the input first.

The untouched recordings are kept as results/videos/raw/<segment>.mp4, so this is safe to re-run.

  uv run scripts/add_intro.py            # 04–10
  uv run scripts/add_intro.py 05-pi-receipt
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from demo_multimodal import DEMOS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "results/videos"
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
SPEED = 2.5  # playback speed of the whole video: intro card / input video and the recording after it
CARD_SECONDS = 5 / SPEED  # image card shown for 5 s of "real time"
SEGMENTS = {
    "04-pi-photo": ("photo", "多模態：真實照片理解（士林夜市）"),
    "05-pi-receipt": ("receipt", "多模態：中文收據 OCR + 驗算找錯"),
    "06-pi-chart": ("chart", "多模態：圖表讀數與計算"),
    "07-pi-wireframe": ("wireframe", "多模態：手繪 wireframe → HTML"),
    "08-pi-geometry": ("geometry", "多模態：看圖解幾何題"),
    "09-video-events": ("video_events", "多模態：影片理解（事件順序 + 計數）"),
    "10-video-mrt": ("video_mrt", "多模態：真實影片理解（台北捷運進站）"),  # video input: played inside the card
}


def wrap(text, font, width):
    lines, cur = [], ""
    for ch in text.replace("\n", ""):
        if font.getlength(cur + ch) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def card(seg: str, size: tuple[int, int]) -> Path:
    key, title = SEGMENTS[seg]
    demo = DEMOS[key]
    W, H = size
    img = Image.new("RGB", (W, H), "#272822")
    d = ImageDraw.Draw(img)
    d.text((40, 30), f"■ {title}", font=ImageFont.truetype(FONT, 38), fill="#a6e22e")
    is_video = demo["file"].endswith(".mp4")
    label = f"輸入影片（{SPEED:g} 倍速播放，接著交給 Nemotron 3.5 Super VL 判讀）" if is_video else "輸入圖片（下一步交給 Nemotron 3.5 Super VL 判讀）"
    d.text((40, 84), label, font=ImageFont.truetype(FONT, 24), fill="#9e9e8f")
    pf = ImageFont.truetype(FONT, 22)
    prompt_lines = wrap("問題：" + demo["prompt"], pf, W - 80)[:4]
    prompt_h = 32 * len(prompt_lines) + 20
    box = (40, 130, W - 40, H - 30 - prompt_h)
    if is_video:
        vw, vh = probe_size(ROOT / "assets" / demo["file"])
        s = min((box[2] - box[0]) / vw, (box[3] - box[1]) / vh)
        pw, ph = int(vw * s) // 2 * 2, int(vh * s) // 2 * 2
        x = box[0] + (box[2] - box[0] - pw) // 2
        y = box[1] + (box[3] - box[1] - ph) // 2
        d.rectangle((x - 4, y - 4, x + pw + 3, y + ph + 3), outline="#75715e", width=2)
        for i, ln in enumerate(prompt_lines):
            d.text((40, H - 20 - prompt_h + 10 + i * 32), ln, font=pf, fill="#f8f8f2")
        out = ROOT / "tmpcode" / f"intro-{seg}.png"
        out.parent.mkdir(exist_ok=True)
        img.save(out)
        return out, (x, y, pw, ph)
    pic = Image.open(ROOT / "assets" / demo["file"]).convert("RGB")
    s = min((box[2] - box[0]) / pic.width, (box[3] - box[1]) / pic.height)
    pic = pic.resize((int(pic.width * s), int(pic.height * s)), Image.LANCZOS)
    x = box[0] + (box[2] - box[0] - pic.width) // 2
    y = box[1] + (box[3] - box[1] - pic.height) // 2
    d.rectangle((x - 4, y - 4, x + pic.width + 3, y + pic.height + 3), outline="#75715e", width=2)
    img.paste(pic, (x, y))
    for i, ln in enumerate(prompt_lines):
        d.text((40, H - 20 - prompt_h + 10 + i * 32), ln, font=pf, fill="#f8f8f2")
    out = ROOT / "tmpcode" / f"intro-{seg}.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    return out, None


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return tuple(map(int, out.split(",")))


def main():
    segs = sys.argv[1:] or list(SEGMENTS)
    raw_dir = VIDEOS / "raw"
    raw_dir.mkdir(exist_ok=True)
    for seg in segs:
        raw = raw_dir / f"{seg}.mp4"
        if not raw.exists():
            shutil.copy2(VIDEOS / f"{seg}.mp4", raw)
        w, h = probe_size(raw)
        png, vbox = card(seg, (w, h))
        sp = SPEED
        if vbox:  # input video plays inside the card, then the recording follows
            x, y, pw, ph = vbox
            src = ROOT / "assets" / DEMOS[SEGMENTS[seg][0]]["file"]
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", str(png), "-i", str(src), "-i", str(raw),
                            "-filter_complex",
                            f"[1:v]setpts=PTS/{sp},scale={pw}:{ph},fps=30,setsar=1[m];[0:v][m]overlay={x}:{y}:shortest=1,format=yuv420p,setsar=1[a];"
                            f"[2:v]setpts=PTS/{sp},fps=30,format=yuv420p,setsar=1[b];[a][b]concat=n=2:v=1:a=0[v]",
                            "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            str(VIDEOS / f"{seg}.mp4")], check=True)
            print(f"{seg}: input video prepended, speed {sp}x")
            continue
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-t", str(CARD_SECONDS), "-i", str(png), "-i", str(raw),
                        "-filter_complex", f"[0:v]format=yuv420p,setsar=1[a];[1:v]setpts=PTS/{SPEED},fps=30,format=yuv420p,setsar=1[b];[a][b]concat=n=2:v=1:a=0[v]",
                        "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(VIDEOS / f"{seg}.mp4")], check=True)
        print(f"{seg}: intro added, speed {SPEED}x")


if __name__ == "__main__":
    main()
