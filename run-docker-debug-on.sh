#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${ROOT_DIR}/.log"

export MRN_DEBUG_GAME_LOGS=1
export MRN_DEBUG_GAME_LOG_DIR="${MRN_DEBUG_GAME_LOG_DIR:-/app/.log}"
export MRN_DEBUG_GAME_LOG_RUN_ID="${MRN_DEBUG_GAME_LOG_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"

echo "Debug game logs: ON"
echo "Host log directory: ${ROOT_DIR}/.log"
echo "Log run id: ${MRN_DEBUG_GAME_LOG_RUN_ID}"

exec "${ROOT_DIR}/run-docker.sh" "$@"
