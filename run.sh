#!/usr/bin/env bash
set -euo pipefail

model_list=(
  "qwen3.7-max"
  "qwen3.7-plus"
  "qwen3.6-plus"
  "deepseek-v4-pro"
  "kimi-k2.6"
  "glm-5.2"
  "glm-5.1"
  "MiniMax/MiniMax-M3"
  "MiniMax/MiniMax-M2.7"
  "xiaomi/mimo-v2.5-pro"
)

for model in "${model_list[@]}"; do
  echo "==================================================================="
  echo ">>> Running benchmark with provider-model: dashscope/${model}"
  echo "==================================================================="

  PYTHONPATH=. ./.venv/bin/python -m autobench.cli \
    --config configs/baseline.json \
    --cases-dir cases-v3 \
    --output-root outputs \
    --provider-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --provider-model "dashscope/${model}" \
    --provider-api-key-env DASHSCOPE_API_KEY
done
