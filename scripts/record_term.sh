#!/usr/bin/env bash
# Record a command in a virtual terminal (asciinema, headless) and render it to MP4 (agg + ffmpeg).
#   [SHOW="short cmd shown on screen"] scripts/record_term.sh <name> "<title>" "<shell command>"
# Output: results/videos/<name>.cast and results/videos/<name>.mp4
# Pauses longer than IDLE (default 3 s) are shortened in the video; the stats printed on screen are real.
set -euo pipefail
cd "$(dirname "$0")/.."
name="$1" title="$2" cmd="$3"
show="${SHOW:-$cmd}"
SIZE="${SIZE:-120x34}" IDLE="${IDLE:-3}"
mkdir -p results/videos
cast="results/videos/$name.cast"

inner="$(mktemp -t record_term).sh"
trap 'rm -f "$inner"' EXIT
cat > "$inner" <<EOS
cd "$PWD"
printf '\033[1;38;5;112m■ %s\033[0m\n\033[38;5;245mNemotron 3.5 Super VL 120B-A12B NVFP4 @ DGX Spark (vLLM) · client: pi on MacBook Air\033[0m\n\n\033[1;32m\$\033[0m %s\n' "\$TITLE" "\$SHOW"
sleep 1
$cmd
sleep 3
EOS
TITLE="$title" SHOW="$show" asciinema rec --headless --overwrite --quiet --window-size "$SIZE" -c "bash $inner" "$cast"

agg --font-family "Menlo,Heiti TC" --font-size 22 --theme monokai --idle-time-limit "$IDLE" --last-frame-duration 4 "$cast" "results/videos/$name.gif" >/dev/null 2>&1
ffmpeg -v error -y -i "results/videos/$name.gif" -vf "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2" -pix_fmt yuv420p \
  -c:v libx264 -crf 20 -movflags +faststart "results/videos/$name.mp4"
rm -f "results/videos/$name.gif"
echo "video: results/videos/$name.mp4"
