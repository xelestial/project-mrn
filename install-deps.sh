#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MRN_BOOTSTRAP_PYTHON:-python3}"
VENV_DIR="${MRN_VENV_DIR:-${ROOT_DIR}/.venv}"
INSTALL_PYTHON=1
INSTALL_WEB=1
DOCKER_BUILD=0

usage() {
  cat <<EOF
Usage: ./install-deps.sh [options]

Installs local development dependencies:
  - Python virtualenv at .venv
  - Python packages from apps/server/requirements.txt
  - Web packages from apps/web/package-lock.json or package.json

Options:
  --python-only    Install only Python dependencies
  --web-only       Install only web dependencies
  --docker-build   Also build Docker images after local dependency install
  -h, --help       Show this help

Environment:
  MRN_BOOTSTRAP_PYTHON  Python used to create .venv (default: python3)
  MRN_VENV_DIR          Virtualenv directory (default: .venv)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python-only)
      INSTALL_PYTHON=1
      INSTALL_WEB=0
      ;;
    --web-only)
      INSTALL_PYTHON=0
      INSTALL_WEB=1
      ;;
    --docker-build)
      DOCKER_BUILD=1
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

install_python_deps() {
  local venv_python="${VENV_DIR}/bin/python"

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Missing Python bootstrap command: ${PYTHON_BIN}" >&2
    exit 1
  fi

  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating virtualenv: ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi

  if [[ ! -x "${venv_python}" ]]; then
    echo "Missing virtualenv Python: ${venv_python}" >&2
    exit 1
  fi

  echo "Installing Python dependencies."
  "${venv_python}" -m pip install --upgrade pip
  "${venv_python}" -m pip install -r "${ROOT_DIR}/apps/server/requirements.txt"
}

install_web_deps() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "Missing npm." >&2
    exit 1
  fi

  echo "Installing web dependencies."
  cd "${ROOT_DIR}/apps/web"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
}

build_docker_images() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Missing Docker CLI." >&2
    exit 1
  fi

  echo "Building Docker images."
  cd "${ROOT_DIR}"
  docker compose build server
}

cd "${ROOT_DIR}"

if [[ "${INSTALL_PYTHON}" == "1" ]]; then
  install_python_deps
fi

if [[ "${INSTALL_WEB}" == "1" ]]; then
  install_web_deps
fi

if [[ "${DOCKER_BUILD}" == "1" ]]; then
  build_docker_images
fi

echo "Dependency installation complete."
