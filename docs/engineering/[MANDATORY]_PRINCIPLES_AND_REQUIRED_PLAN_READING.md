# [MANDATORY] Principles And Required Plan Reading

Status: ACTIVE  
Updated: 2026-04-05  
Scope: engine / server / web / contracts

## Absolute Start Rule

Before any implementation work:

1. open this document first
2. open the required plans in the order listed below
3. only then begin code changes

This rule applies to all work sizes:
- small patch
- medium refactor
- large architecture change

## Required Reading Order Before Coding

Read these in order:

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/Game-Rules.md`
3. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `PLAN/PLAN_STATUS_INDEX.md`
5. `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
6. `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

## Mandatory Engineering Principles

### P-00 Encoding Safety

- All text files must remain `UTF-8` with `LF`.
- `CP-949` is forbidden.
- Do not rewrite file encoding because PowerShell output looks broken.
- If visible user-facing wording changes, check the string/i18n plans first.
- Prefer shared text resources over inline literals.

### P-01 DI And Boundary Discipline

- Human and AI decisions must follow the same request/response contract.
- Route behavior through provider / adapter / contract boundaries, not hidden direct coupling.
- Keep mark / weather / fortune / prompt policy logic injectable where applicable.

### P-02 Low Coupling / High Maintainability

- Avoid scattering gameplay wording or rules across unrelated components.
- Keep selectors, renderers, and transport layers clearly separated.
- Prefer stable canonical payloads over UI-generated pseudo-contracts.

### P-03 Ordering And Determinism

- Preserve:
  - `decision_requested`
  - `decision_resolved` or `decision_timeout_fallback`
  - domain events
- Keep stream ordering deterministic.
- Replay/live views must read the same canonical event order.

### P-04 Testing Discipline

- Complex changes require plan-first work.
- Behavioral changes should add or update tests.
- Human-play changes should be validated with browser-level coverage when practical.

### P-05 UX Safety

- Only actionable prompts should block the local player.
- Non-actionable remote activity should be shown as observer/theater information.
- Runtime errors and warnings must not replace core gameplay narrative.

### P-06 Documentation Policy

- Plans live on `main`.
- Update relevant plan docs when the implementation direction changes.
- Leave a summary in:
  - `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

### P-07 Work Execution Policy

- Every task, small or large, must leave a worklog summary.
- Logic-heavy or architecture-heavy changes must start from a plan document.

### P-08 String Ownership

- User-facing strings should live in shared resources/catalogs.
- Do not introduce new inline visible strings unless there is a strong temporary reason.
- Any string or wording work must check the current active web locale/resources and worklog.

## Mandatory Working Checklist

Before merge or handoff, confirm:

- [ ] required documents were read first
- [ ] rule source matches implementation intent
- [ ] decision contract ordering was preserved
- [ ] UTF-8 / LF policy was preserved
- [ ] relevant tests were run or explicitly noted as not run
- [ ] worklog entry was added

## Encoding Incident Prevention Note

If text appears broken:

- do not guess the encoding and rewrite files blindly
- check whether the terminal output is the problem instead of the file itself
- verify against the string resource files and plan docs first

When touching user-facing text, always re-check:

- `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
- `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
- `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
