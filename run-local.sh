#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-9090}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-5173}"

SERVER_PID=""
WEB_PID=""

cleanup() {
  local exit_code=$?
  if [[ -n "${WEB_PID}" ]] && kill -0 "${WEB_PID}" 2>/dev/null; then
    kill "${WEB_PID}" 2>/dev/null || true
    wait "${WEB_PID}" 2>/dev/null || true
  fi
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing virtualenv interpreter: ${ROOT_DIR}/.venv/bin/python" >&2
  exit 1
fi

if [[ ! -f "apps/web/package.json" ]]; then
  echo "Missing web package.json: ${ROOT_DIR}/apps/web/package.json" >&2
  exit 1
fi

echo "Starting server on http://${SERVER_HOST}:${SERVER_PORT}"
.venv/bin/python -m uvicorn apps.server.src.app:app --host "${SERVER_HOST}" --port "${SERVER_PORT}" &
SERVER_PID=$!

echo "Starting web client on http://${WEB_HOST}:${WEB_PORT}"
(
  cd "${ROOT_DIR}/apps/web"
  npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" --strictPort
) &
WEB_PID=$!

wait "${SERVER_PID}" "${WEB_PID}"
