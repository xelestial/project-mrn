#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MRN_PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
SERVER_HOST="${MRN_SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${MRN_SERVER_PORT:-9090}"
WEB_HOST="${MRN_WEB_HOST:-127.0.0.1}"
WEB_PORT="${MRN_WEB_PORT:-9000}"
SERVER_HEALTH_URL="http://${SERVER_HOST}:${SERVER_PORT}/health"

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

usage() {
  cat <<EOF
Usage: ./run-local.sh

Starts the local FastAPI backend and Vite web client together.

Run ./install-deps.sh first when local dependencies are missing.

Environment:
  MRN_PYTHON_BIN     Python interpreter path (default: .venv/bin/python)
  MRN_SERVER_HOST    Backend host (default: 127.0.0.1)
  MRN_SERVER_PORT    Backend port (default: 9090)
  MRN_WEB_HOST       Web host (default: 127.0.0.1)
  MRN_WEB_PORT       Web port (default: 9000)
  MRN_RELOAD=1       Start backend uvicorn with --reload
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

trap cleanup EXIT INT TERM

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime: ${PYTHON_BIN}" >&2
  echo "Run ./install-deps.sh first, or set MRN_PYTHON_BIN." >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/apps/web/package.json" ]]; then
  echo "Missing web package.json: ${ROOT_DIR}/apps/web/package.json" >&2
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/apps/web/node_modules" ]]; then
  echo "Missing web dependencies: ${ROOT_DIR}/apps/web/node_modules" >&2
  echo "Run ./install-deps.sh first." >&2
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"${SERVER_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Server port ${SERVER_PORT} is already in use." >&2
    echo "Health check URL: ${SERVER_HEALTH_URL}" >&2
    exit 1
  fi

  if lsof -iTCP:"${WEB_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Web port ${WEB_PORT} is already in use." >&2
    exit 1
  fi
fi

SERVER_ARGS=(apps.server.src.app:app --host "${SERVER_HOST}" --port "${SERVER_PORT}")
if [[ "${MRN_RELOAD:-0}" == "1" ]]; then
  SERVER_ARGS+=(--reload)
fi

cd "${ROOT_DIR}"

echo "Starting MRN server: http://${SERVER_HOST}:${SERVER_PORT}"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m uvicorn "${SERVER_ARGS[@]}" &
SERVER_PID=$!

echo "Starting MRN web client: http://${WEB_HOST}:${WEB_PORT}"
(
  cd "${ROOT_DIR}/apps/web"
  npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" --strictPort
) &
WEB_PID=$!

wait "${SERVER_PID}" "${WEB_PID}"
