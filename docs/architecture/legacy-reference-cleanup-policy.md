# Legacy Reference Cleanup Policy

Status: `ACTIVE`  
Updated: `2026-03-31`

## Goal

Prevent new implementation code from coupling to legacy paths (`GPT/`, `CLAUDE/`, `frontend/`) while preserving historical planning records.

## Scope Split

Strict scope (must be zero legacy references):

- `apps/`
- `packages/`
- `tools/`

Historical scope (reference-only, not strict-fail):

- `PLAN/`
- archived proposal/review documents

## Enforcement

Hard gate command:

```bash
python tools/legacy_path_audit.py --roots apps packages tools --strict
```

Current baseline (`2026-03-31`):

- `GPT/`: 0
- `CLAUDE/`: 0
- `frontend/`: 0

## Operational Rule

1. New runtime/frontend/backend code must use `apps/*` + `packages/*` paths only.
2. If a PR introduces a legacy-path reference in strict scope, fix it before merge.
3. Historical `PLAN/` references are allowed only when they are archival context and not implementation instructions.

## Related Documents

- `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
- `PLAN/PLAN_STATUS_INDEX.md`
- `PLAN/[PLAN]_IMPLEMENTATION_DOCUMENT_USAGE_GUIDE.md`
