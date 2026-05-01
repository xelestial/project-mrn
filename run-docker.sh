#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${MRN_COMPOSE_FILE:-${ROOT_DIR}/docker-compose.yml}"
COMPOSE_PROJECT="${MRN_COMPOSE_PROJECT:-project-mrn}"
SERVICES=(redis server prompt-timeout-worker command-wakeup-worker)
DETACHED=0
BUILD=1
PULL=0
ACTION="up"

usage() {
  cat <<EOF
Usage: ./run-docker.sh [options]

Runs the Redis-backed Docker runtime stack:
  redis, server, prompt-timeout-worker, command-wakeup-worker

Options:
  -d, --detached   Run in the background
  --no-build       Do not build images before starting
  --pull           Pull service images before starting
  down             Stop and remove the Docker runtime stack
  logs             Follow Docker runtime logs
  -h, --help       Show this help

Environment:
  MRN_COMPOSE_FILE     Compose file path (default: docker-compose.yml)
  MRN_COMPOSE_PROJECT  Compose project name (default: project-mrn)
EOF
}

compose() {
  docker compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--detached)
      DETACHED=1
      ;;
    --no-build)
      BUILD=0
      ;;
    --pull)
      PULL=1
      ;;
    down|logs)
      ACTION="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing Docker CLI." >&2
  exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Missing compose file: ${COMPOSE_FILE}" >&2
  exit 1
fi

cd "${ROOT_DIR}"

case "${ACTION}" in
  down)
    compose down
    ;;
  logs)
    compose logs -f "${SERVICES[@]}"
    ;;
  up)
    UP_ARGS=(up)
    if [[ "${BUILD}" == "1" ]]; then
      UP_ARGS+=(--build)
    fi
    if [[ "${PULL}" == "1" ]]; then
      UP_ARGS+=(--pull always)
    fi
    if [[ "${DETACHED}" == "1" ]]; then
      UP_ARGS+=(-d)
    fi
    UP_ARGS+=("${SERVICES[@]}")

    echo "Starting MRN Docker runtime with project '${COMPOSE_PROJECT}'."
    compose "${UP_ARGS[@]}"
    ;;
esac
