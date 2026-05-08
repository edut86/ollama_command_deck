#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Neither docker compose nor docker-compose was found." >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ -f docker-compose.override.yml ]]; then
  COMPOSE_FILES+=(-f docker-compose.override.yml)
fi
if [[ -f docker-compose.gpu.yml ]]; then
  COMPOSE_FILES+=(-f docker-compose.gpu.yml)
fi

remove_volumes="n"
remove_override="n"
if [[ "${1:-}" == "--volumes" ]]; then
  remove_volumes="y"
fi
if [[ "${2:-}" == "--remove-override" || "${1:-}" == "--remove-override" ]]; then
  remove_override="y"
fi

echo "This will stop Command Deck containers and remove local Docker images."
echo "Project: $(basename "$PWD")"
echo
if [[ "$remove_volumes" != "y" ]]; then
  read -r -p "Also remove Docker volumes with app data/config? This deletes sessions/users/config. [y/N]: " remove_volumes
fi

DOWN_ARGS=(down --remove-orphans --rmi local)
if [[ "$remove_volumes" =~ ^[Yy]$ ]]; then
  DOWN_ARGS+=(--volumes)
fi

"${COMPOSE[@]}" "${COMPOSE_FILES[@]}" "${DOWN_ARGS[@]}"

if [[ "$remove_override" != "y" && -f docker-compose.override.yml ]]; then
  read -r -p "Remove local docker-compose.override.yml too? [y/N]: " remove_override
fi
if [[ "$remove_override" =~ ^[Yy]$ && -f docker-compose.override.yml ]]; then
  rm -f docker-compose.override.yml
  echo "Removed docker-compose.override.yml"
fi

echo "Docker uninstall complete."
