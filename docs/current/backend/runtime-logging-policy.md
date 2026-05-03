# Runtime Logging Policy

Status: `ACTIVE`  
Updated: `2026-03-31`  
Scope: `apps/server` runtime and transport services

## Purpose

Define log retention defaults and runtime rotation behavior for the FastAPI server path.

## Structured Logging Baseline

Runtime logs are JSON lines with stable core fields:

- `event`
- `ts_ms`
- contextual fields (`session_id`, `request_id`, `player_id`, `seq`, ...)

Primary logger: `mrn.server`  
Bootstrap point: `apps/server/src/state.py`

## Rotation Settings (Environment)

Configured via `apps/server/src/config/runtime_settings.py`.

- `MRN_LOG_LEVEL` (default: `INFO`)
- `MRN_LOG_FILE_PATH` (default: empty, file logging disabled)
- `MRN_LOG_FILE_MAX_BYTES` (default: `5242880`, minimum: `1024`)
- `MRN_LOG_FILE_BACKUP_COUNT` (default: `5`, minimum: `1`)

Behavior:

- Always logs to stdout (stream handler).
- Adds rotating file handler only when `MRN_LOG_FILE_PATH` is set.
- Rotation uses max-bytes + backup-count policy.

## Recommended Profiles

Local dev:

- `MRN_LOG_LEVEL=DEBUG`
- `MRN_LOG_FILE_PATH` unset (stdout only)

Shared dev/QA:

- `MRN_LOG_LEVEL=INFO`
- `MRN_LOG_FILE_PATH=result/server/server.log`
- `MRN_LOG_FILE_MAX_BYTES=5242880`
- `MRN_LOG_FILE_BACKUP_COUNT=5`

Load test / long runs:

- `MRN_LOG_LEVEL=INFO`
- `MRN_LOG_FILE_PATH=result/server/server.log`
- `MRN_LOG_FILE_MAX_BYTES=10485760`
- `MRN_LOG_FILE_BACKUP_COUNT=10`

## Verification

Covered by:

- `apps/server/tests/test_runtime_settings.py`
- `apps/server/tests/test_structured_log.py`

Operational sanity check:

1. Start server with file log env vars set.
2. Trigger session lifecycle + prompt timeout flow.
3. Confirm `server.log` is created and JSON lines are appended.
4. Force large output and verify rotated backups are created.
