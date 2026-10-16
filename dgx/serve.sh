#!/usr/bin/env bash
# Serve NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 on a DGX Spark (GB10) with vLLM.
# Follows the model card's "Quick Start" (DGX Spark only) recipe, with the LiLiCorr drafter.
# Usage (on the DGX):  ./serve.sh            # start in background
#                      docker logs -f nemotron35vl
set -euo pipefail

IMAGE="${IMAGE:-vllm/vllm-openai:nightly-3f1bcfd82bb2e93fcd364fc7a5491718453a77e2}"
MODEL="nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4"
DRAFT_MODEL="nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-LiLiCorr"
PORT="${PORT:-8000}"
NAME="${NAME:-nemotron35vl}"

docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" \
  --gpus all --ipc=host --restart unless-stopped \
  -p "${PORT}:8000" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v "$HOME/.cache/vllm:/root/.cache/vllm" \
  -e HF_HUB_OFFLINE=1 \
  ${HF_TOKEN:+-e HF_TOKEN} \
  "$IMAGE" \
  "$MODEL" \
  --served-model-name nemotron-3.5-super-vl \
  --host 0.0.0.0 --port 8000 \
  --max-num-seqs 1 \
  --trust-remote-code \
  --gpu-memory-utilization 0.75 \
  --max-num-batched-tokens 8192 \
  --speculative_config.model "$DRAFT_MODEL" \
  --speculative_config.num_speculative_tokens 7 \
  --speculative_config.method dflash \
  --mamba-backend flashinfer \
  --mamba-ssm-cache-dtype float16 \
  --enable-mamba-cache-stochastic-rounding \
  --mamba-cache-philox-rounds 5 \
  --enable-mamba-shared-prefix-checkpoint \
  --video-pruning-rate 0.5 \
  --media-io-kwargs '{"video": {"fps": 2, "num_frames": 256}}' \
  --block-size 64 \
  --prefix-match-unit 64 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser nemotron_v3 \
  "$@"

echo "Started container '$NAME' on port $PORT. Follow logs: docker logs -f $NAME"
