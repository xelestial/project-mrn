from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.services.stream_service import StreamService


class ViewCommitStreamServiceTests(unittest.TestCase):
    def test_publish_keeps_event_payload_plain_without_auto_view_commit(self) -> None:
        async def _run() -> tuple[dict, list[dict]]:
            service = StreamService()
            event = await service.publish("sess_view_commit_1", "event", {"event_type": "round_start", "round_index": 1})
            snapshot = await service.snapshot("sess_view_commit_1")
            return event.to_dict(), [message.to_dict() for message in snapshot]

        event, snapshot = asyncio.run(_run())

        self.assertNotIn("view_state", event["payload"])
        self.assertEqual([message["type"] for message in snapshot], ["event"])

    def test_prompt_publish_does_not_create_live_view_commit(self) -> None:
        async def _run() -> dict | None:
            service = StreamService()
            await service.publish(
                "sess_view_commit_prompt",
                "prompt",
                {
                    "event_type": "prompt_required",
                    "request_id": "req_prompt_1",
                    "prompt_instance_id": 7,
                    "resume_token": "resume_prompt_1",
                    "frame_id": "frame_prompt_1",
                    "module_id": "module_prompt_1",
                    "module_type": "MovementPromptModule",
                    "module_cursor": "await_prompt",
                    "request_type": "movement",
                    "player_id": 1,
                    "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                },
            )
            latest = await service.latest_view_commit_message_for_viewer(
                "sess_view_commit_prompt",
                ViewerContext(role="seat", session_id="sess_view_commit_prompt", player_id=1, seat=1),
            )
            return latest

        latest = asyncio.run(_run())

        self.assertIsNone(latest)
