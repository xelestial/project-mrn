from __future__ import annotations

from apps.server.src.config.runtime_settings import load_runtime_settings
from apps.server.src.infra.structured_log import configure_structured_logging
from apps.server.src.services.persistence import JsonFileSessionStore, JsonFileStreamStore
from apps.server.src.services.prompt_service import PromptService
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
session_service = SessionService(session_store=session_store)
stream_service = StreamService(stream_store=stream_store)
prompt_service = PromptService()
runtime_service = RuntimeService(
    session_service=session_service,
    stream_service=stream_service,
    watchdog_timeout_ms=runtime_settings.runtime_watchdog_timeout_ms,
)
