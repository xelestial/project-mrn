# policy_hooks.py

Role:
- Provides lightweight before/after decision hooks for `choose_*` policy methods.
- Supports in-memory trace recording and engine action-log emission without changing core heuristic logic.

Key classes:
- `PolicyHookDispatcher`
- `PolicyDecisionTraceRecorder`
- `PolicyDecisionLogHook`
