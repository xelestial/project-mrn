from __future__ import annotations

from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService

session_service = SessionService()
stream_service = StreamService()
prompt_service = PromptService()
runtime_service = RuntimeService(session_service=session_service, stream_service=stream_service)
