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

if [[ -z "${OLLAMA_WEB_TLS_HOSTS:-}" ]]; then
  tls_hosts=("localhost" "$(hostname)")
  if command -v hostname >/dev/null 2>&1; then
    while read -r ip; do
      [[ -n "$ip" ]] && tls_hosts+=("$ip")
    done < <(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
  fi
  if command -v ip >/dev/null 2>&1; then
    while read -r ip; do
      [[ -n "$ip" ]] && tls_hosts+=("$ip")
    done < <(ip -o -4 addr show scope global 2>/dev/null | awk '{split($4, a, "/"); print a[1]}' || true)
  fi
  OLLAMA_WEB_TLS_HOSTS="$(printf '%s\n' "${tls_hosts[@]}" | awk 'NF && !seen[$0]++' | paste -sd, -)"
  export OLLAMA_WEB_TLS_HOSTS
fi

STT_MODE="${STT_MODE:-auto}"
COMPOSE_FILES=(-f docker-compose.yml)
if [[ -f docker-compose.override.yml ]]; then
  COMPOSE_FILES+=(-f docker-compose.override.yml)
fi
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

scheme="http"
if "${COMPOSE[@]}" "${COMPOSE_FILES[@]}" config 2>/dev/null | grep -q "WEB_CERT_FILE:"; then
  scheme="https"
fi
echo
echo "Open Command Deck at ${scheme}://localhost:8765"
if [[ "$scheme" == "https" ]]; then
  echo "For microphone access from another device, use https://<this-host-or-ip>:8765 and accept/trust the self-signed certificate."
  echo "Certificate names/IPs: ${OLLAMA_WEB_TLS_HOSTS:-localhost}"
fi
