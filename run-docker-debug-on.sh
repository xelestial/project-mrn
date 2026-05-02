#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${ROOT_DIR}/.log"

export MRN_DEBUG_GAME_LOGS=1
export MRN_DEBUG_GAME_LOG_DIR="${MRN_DEBUG_GAME_LOG_DIR:-/app/.log}"

echo "Debug game logs: ON"
echo "Host log directory: ${ROOT_DIR}/.log"

exec "${ROOT_DIR}/run-docker.sh" "$@"
