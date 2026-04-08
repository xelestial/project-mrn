#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv311/bin/python"
HOST="${MRN_SERVER_HOST:-127.0.0.1}"
PORT="${MRN_SERVER_PORT:-8001}"
HEALTH_URL="http://${HOST}:${PORT}/health"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime: ${PYTHON_BIN}" >&2
  echo "Create /Users/sil/Workspace/project-mrn/.venv311 first." >&2
  exit 1
fi

if command -v curl >/dev/null 2>&1 && curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "MRN server is already running at http://${HOST}:${PORT}"
  echo "Health check: ${HEALTH_URL}"
  exit 0
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use by another process." >&2
  echo "If this is the MRN server, use ${HEALTH_URL} to verify it." >&2
  exit 1
fi

cd "${ROOT_DIR}"
PYTHONPATH="${ROOT_DIR}" exec "${PYTHON_BIN}" -m uvicorn apps.server.src.app:app --host "${HOST}" --port "${PORT}"
