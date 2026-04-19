from __future__ import annotations

from apps.server.src.config.runtime_settings import load_runtime_settings
from apps.server.src.infra.structured_log import configure_structured_logging
from apps.server.src.services.persistence import JsonFileSessionStore, JsonFileStreamStore
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.room_service import RoomService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService

runtime_settings = load_runtime_settings()
configure_structured_logging(
    level=runtime_settings.log_level,
    file_path=runtime_settings.log_file_path,
    max_bytes=runtime_settings.log_file_max_bytes,
    backup_count=runtime_settings.log_file_backup_count,
)
session_store = (
    JsonFileSessionStore(runtime_settings.session_store_path)
    if runtime_settings.session_store_path
    else None
)
stream_store = (
    JsonFileStreamStore(runtime_settings.stream_store_path)
    if runtime_settings.stream_store_path
    else None
)
session_service = SessionService(
    session_store=session_store,
    max_persisted_sessions=runtime_settings.session_store_max_sessions,
    restart_recovery_policy=runtime_settings.restart_recovery_policy,
)
stream_service = StreamService(
    stream_store=stream_store,
    max_persisted_sessions=runtime_settings.stream_store_max_sessions,
    player_name_resolver=lambda session_id: session_service.player_display_names(session_id),
)
prompt_service = PromptService()
runtime_service = RuntimeService(
    session_service=session_service,
    stream_service=stream_service,
    prompt_service=prompt_service,
    watchdog_timeout_ms=runtime_settings.runtime_watchdog_timeout_ms,
)
room_service = RoomService(
    session_service=session_service,
    room_store=session_store,
)
runtime_service.add_session_finished_callback(room_service.handle_session_finished)
