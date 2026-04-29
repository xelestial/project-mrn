from __future__ import annotations

from apps.server.src.config.runtime_settings import load_runtime_settings
from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.infra.structured_log import configure_structured_logging
from apps.server.src.services.persistence import (
    JsonFileSessionStore,
    JsonFileStreamStore,
    RedisRoomStore,
    RedisSessionStore,
)
from apps.server.src.services.archive_service import LocalJsonArchiveService
from apps.server.src.services.command_wakeup_worker import CommandStreamWakeupWorker
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.realtime_persistence import (
    RedisCommandStore,
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
)
from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorker
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
redis_connection = (
    RedisConnection(
        RedisConnectionSettings(
            url=runtime_settings.redis_url,
            key_prefix=runtime_settings.redis_key_prefix,
            socket_timeout_ms=runtime_settings.redis_socket_timeout_ms,
        )
    )
    if runtime_settings.redis_url
    else None
)
if redis_connection is not None:
    session_store = RedisSessionStore(redis_connection)
    room_store = RedisRoomStore(redis_connection)
    stream_backend = RedisStreamStore(redis_connection)
    prompt_store = RedisPromptStore(redis_connection)
    runtime_state_store = RedisRuntimeStateStore(redis_connection)
    game_state_store = RedisGameStateStore(redis_connection)
    command_store = RedisCommandStore(redis_connection)
    session_storage_backend = "redis"
    room_storage_backend = "redis"
else:
    session_store = (
        JsonFileSessionStore(runtime_settings.session_store_path)
        if runtime_settings.session_store_path
        else None
    )
    room_store = session_store
    stream_backend = None
    prompt_store = None
    runtime_state_store = None
    game_state_store = None
    command_store = None
    session_storage_backend = "json_file" if runtime_settings.session_store_path else "memory"
    room_storage_backend = session_storage_backend
stream_store = (
    JsonFileStreamStore(runtime_settings.stream_store_path)
    if runtime_settings.stream_store_path
    else None
)
if stream_backend is not None:
    stream_storage_backend = "redis"
else:
    stream_storage_backend = "json_file" if runtime_settings.stream_store_path else "memory"
session_service = SessionService(
    session_store=session_store,
    max_persisted_sessions=runtime_settings.session_store_max_sessions,
    restart_recovery_policy=runtime_settings.restart_recovery_policy,
)
stream_service = StreamService(
    stream_store=stream_store,
    stream_backend=stream_backend,
    game_state_store=game_state_store,
    command_store=command_store,
    max_persisted_sessions=runtime_settings.stream_store_max_sessions,
    player_name_resolver=lambda session_id: session_service.player_display_names(session_id),
)
prompt_service = PromptService(prompt_store=prompt_store, command_store=command_store)
runtime_service = RuntimeService(
    session_service=session_service,
    stream_service=stream_service,
    prompt_service=prompt_service,
    watchdog_timeout_ms=runtime_settings.runtime_watchdog_timeout_ms,
    runtime_state_store=runtime_state_store,
    game_state_store=game_state_store,
)
prompt_timeout_worker = PromptTimeoutWorker(
    prompt_service=prompt_service,
    runtime_service=runtime_service,
    stream_service=stream_service,
)
command_wakeup_worker = (
    CommandStreamWakeupWorker(
        command_store=command_store,
        session_service=session_service,
        runtime_service=runtime_service,
        poll_interval_ms=runtime_settings.command_wakeup_worker_poll_interval_ms,
    )
    if command_store is not None
    else None
)
room_service = RoomService(
    session_service=session_service,
    room_store=room_store,
)
archive_service = (
    LocalJsonArchiveService(
        session_service=session_service,
        stream_service=stream_service,
        room_service=room_service,
        prompt_service=prompt_service,
        runtime_service=runtime_service,
        game_state_store=game_state_store,
        command_store=command_store,
        archive_dir=runtime_settings.game_log_archive_path,
        hot_retention_seconds=runtime_settings.archive_hot_retention_seconds,
        redis_key_prefix=runtime_settings.redis_key_prefix,
    )
    if redis_connection is not None and runtime_settings.game_log_archive_path
    else None
)
if archive_service is not None:
    runtime_service.add_session_finished_callback(archive_service.handle_session_finished)
runtime_service.add_session_finished_callback(room_service.handle_session_finished)
