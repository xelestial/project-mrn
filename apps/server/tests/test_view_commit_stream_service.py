from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.services.stream_service import StreamService


class ViewCommitStreamServiceTests(unittest.TestCase):
    def test_publish_keeps_event_payload_plain_and_appends_view_commit(self) -> None:
        async def _run() -> tuple[dict, list[dict]]:
            service = StreamService()
            event = await service.publish("sess_view_commit_1", "event", {"event_type": "round_start", "round_index": 1})
            snapshot = await service.snapshot("sess_view_commit_1")
            return event.to_dict(), [message.to_dict() for message in snapshot]

        event, snapshot = asyncio.run(_run())

        self.assertNotIn("view_state", event["payload"])
        self.assertEqual([message["type"] for message in snapshot], ["event", "view_commit"])
        commit = snapshot[-1]
        self.assertEqual(commit["payload"]["schema_version"], 1)
        self.assertEqual(commit["payload"]["commit_seq"], commit["seq"])
        self.assertEqual(commit["payload"]["source_event_seq"], event["seq"])
        self.assertEqual(commit["payload"]["viewer"]["role"], "spectator")
        self.assertIn("runtime", commit["payload"])
        self.assertIn("view_state", commit["payload"])

    def test_prompt_view_commit_marks_prompt_issue_commit_seq_for_target_viewer(self) -> None:
        async def _run() -> dict:
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
            assert latest is not None
            return latest

        latest = asyncio.run(_run())

        active_prompt = latest["payload"]["view_state"]["prompt"]["active"]
        self.assertEqual(active_prompt["request_id"], "req_prompt_1")
        self.assertEqual(active_prompt["view_commit_seq"], latest["payload"]["commit_seq"])
