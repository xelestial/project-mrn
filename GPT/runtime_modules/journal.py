from __future__ import annotations

from .contracts import GameRuntimeState, ModuleJournalEntry, ModuleRef


def append_journal_entry(
    runtime: GameRuntimeState,
    *,
    frame_id: str,
    module: ModuleRef,
    event_types: list[str] | None = None,
    error: str = "",
) -> ModuleJournalEntry:
    entry = ModuleJournalEntry(
        module_id=module.module_id,
        frame_id=frame_id,
        status=module.status,
        idempotency_key=module.idempotency_key,
        event_types=list(event_types or []),
        error=error,
    )
    runtime.module_journal.append(entry)
    return entry
