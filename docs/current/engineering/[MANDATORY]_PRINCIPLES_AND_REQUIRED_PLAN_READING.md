# [MANDATORY] Principles And Required Plan Reading

Status: ACTIVE  
Updated: 2026-05-13
Scope: engine / server / web / contracts

## Absolute Start Rule

Before any implementation work:

1. open this document first
2. open the required plans in the order listed below
3. write the task's completion criteria before editing code
4. only then begin code changes

This rule applies to all work sizes:
- small patch
- medium refactor
- large architecture change

## Mandatory Pre-Implementation Contract

Before code changes, the implementer must state the concrete contract for the
task. This is required even for small changes because passing tests alone does
not prove that the intended responsibility moved, disappeared, or stayed
bounded.

Required fields:

- Goal: what behavior, responsibility, or document state must change.
- Completion criteria: the observable conditions that make the task done.
- Non-goals: related work that must not be pulled into the change.
- Protected boundaries: files, runtime contracts, protocol shapes, or ownership
  rules that must not be broken.
- Verification commands: the focused tests, broader tests, gates, or manual
  checks that will prove the completion criteria.
- Responsibility check: for architecture/runtime work, explicitly say which
  responsibility was removed, moved, or intentionally left in place.

The final report must compare the result against these fields. Do not report a
task as complete merely because the edited files compile or because a broad test
suite passed.

## Required Reading Order Before Coding

Read these in order:

1. `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/current/Game-Rules.md`
3. `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `docs/current/planning/PLAN_STATUS_INDEX.md`
5. `docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`
6. `docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

## Mandatory Engineering Principles

### P-00 Encoding Safety

- All text files must remain `UTF-8` with `LF`.
- `CP-949` is forbidden.
- Do not rewrite file encoding because PowerShell output looks broken.
- If visible user-facing wording changes, check the string/i18n plans first.
- Prefer shared text resources over inline literals.

### P-01 DI And Boundary Discipline

- Human and AI decisions must follow the same request/response contract.
- Canonical contract form: `DecisionRequest -> DecisionResponse`.
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
  - `docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

### P-07 Work Execution Policy

- Every task, small or large, must leave a worklog summary.
- Logic-heavy or architecture-heavy changes must start from a plan document.
- 작업 원칙 - 소규모/대규모 작업에 관계 없이 어떤 일을 했는지 요약하여 작업 일지 문서에 남긴다.
- 작업 원칙 - 로직 등 복잡한 변경은 계획 문서를 먼저 작성한다.

### P-08 String Ownership

- User-facing strings should live in shared resources/catalogs.
- Do not introduce new inline visible strings unless there is a strong temporary reason.
- Any string or wording work must check the current active web locale/resources and worklog.

### P-09 Completion Criteria Discipline

- Every implementation starts by making the completion criteria explicit.
- The criteria must be specific enough to falsify: a reviewer should be able to
  say whether each item passed or failed.
- Verification must be chosen from the criteria, not from habit.
- Architecture work must include a responsibility check, not only behavior
  tests.
- If the implementation changes direction, update the criteria before
  continuing.

## Mandatory Working Checklist

Before merge or handoff, confirm:

- [ ] required documents were read first
- [ ] task goal, completion criteria, non-goals, protected boundaries, and
      verification commands were stated before code edits
- [ ] rule source matches implementation intent
- [ ] decision contract ordering was preserved
- [ ] UTF-8 / LF policy was preserved
- [ ] relevant tests were run or explicitly noted as not run
- [ ] final report compared the result against the stated completion criteria
- [ ] worklog entry was added

## Encoding Incident Prevention Note

If text appears broken:

- do not guess the encoding and rewrite files blindly
- check whether the terminal output is the problem instead of the file itself
- verify against the string resource files and plan docs first

When touching user-facing text, always re-check:

- `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
- `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
- `docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
