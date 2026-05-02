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

"${COMPOSE[@]}" build piper web

if [[ "$COMPOSE_KIND" == "v1" ]]; then
  echo "docker-compose v1 detected; removing stale containers to avoid KeyError: ContainerConfig"
  "${COMPOSE[@]}" rm -sf piper web
fi

"${COMPOSE[@]}" up -d piper web
"${COMPOSE[@]}" ps piper web
