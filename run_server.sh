#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MRN_PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
HOST="${MRN_SERVER_HOST:-127.0.0.1}"
PORT="${MRN_SERVER_PORT:-9090}"
APP_MODULE="${MRN_SERVER_APP:-apps.server.src.app:app}"
HEALTH_URL="http://${HOST}:${PORT}/health"

usage() {
  cat <<EOF
Usage: ./run_server.sh

Environment:
  MRN_PYTHON_BIN     Python interpreter path (default: .venv/bin/python)
  MRN_SERVER_HOST    Backend host (default: 127.0.0.1)
  MRN_SERVER_PORT    Backend port (default: 9090)
  MRN_SERVER_APP     ASGI app module (default: apps.server.src.app:app)
  MRN_RELOAD=1       Start uvicorn with --reload
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime: ${PYTHON_BIN}" >&2
  echo "Create the virtualenv first, or set MRN_PYTHON_BIN." >&2
  exit 1
fi

if command -v curl >/dev/null 2>&1 && curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "MRN server is already healthy at ${HEALTH_URL}"
  exit 0
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use." >&2
  echo "Health check attempted: ${HEALTH_URL}" >&2
  exit 1
fi

UVICORN_ARGS=("${APP_MODULE}" --host "${HOST}" --port "${PORT}")
if [[ "${MRN_RELOAD:-0}" == "1" ]]; then
  UVICORN_ARGS+=(--reload)
fi

cd "${ROOT_DIR}"
echo "Starting MRN server: http://${HOST}:${PORT}"
PYTHONPATH="${ROOT_DIR}" exec "${PYTHON_BIN}" -m uvicorn "${UVICORN_ARGS[@]}"
