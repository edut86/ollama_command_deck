#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
  COMPOSE_KIND="v2"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
  COMPOSE_KIND="v1"
else
  echo "error: neither 'docker compose' nor 'docker-compose' is available" >&2
  exit 2
fi

echo "Using ${COMPOSE[*]} (${COMPOSE_KIND})"

STT_MODE="${STT_MODE:-auto}"
COMPOSE_FILES=(-f docker-compose.yml)
if [[ "$STT_MODE" == "auto" ]]; then
  if command -v nvidia-smi >/dev/null 2>&1 && docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
    STT_MODE="gpu"
  else
    STT_MODE="cpu"
  fi
fi

if [[ "$STT_MODE" == "gpu" ]]; then
  COMPOSE_FILES+=(-f docker-compose.gpu.yml)
  export STT_MODE=gpu
  export WHISPER_DEVICE_INDEX="${WHISPER_DEVICE_INDEX:-0}"
  echo "STT mode: gpu (NVIDIA runtime enabled)"
else
  export STT_MODE=cpu
  echo "STT mode: cpu"
fi

"${COMPOSE[@]}" "${COMPOSE_FILES[@]}" build piper web

if [[ "$COMPOSE_KIND" == "v1" ]]; then
  echo "docker-compose v1 detected; removing stale containers to avoid KeyError: ContainerConfig"
  "${COMPOSE[@]}" "${COMPOSE_FILES[@]}" rm -sf piper web
fi

"${COMPOSE[@]}" "${COMPOSE_FILES[@]}" up -d piper web
"${COMPOSE[@]}" "${COMPOSE_FILES[@]}" ps piper web
