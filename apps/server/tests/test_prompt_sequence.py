from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.server.src.domain.prompt_sequence import runtime_prompt_sequence_seed
from apps.server.src.services.runtime_service import RuntimeDecisionResume


class PromptSequenceTests(unittest.TestCase):
    def test_seed_uses_explicit_prompt_instance_id_for_opaque_resume_request_id(self) -> None:
        state = SimpleNamespace(
            prompt_sequence=19,
            pending_prompt_instance_id=19,
            pending_prompt_request_id="req_current_opaque",
        )
        checkpoint = {
            "decision_resume_request_id": "req_previous_opaque",
            "decision_resume_request_type": "trick_tile_target",
            "decision_resume_player_id": 1,
            "decision_resume_prompt_instance_id": 18,
            "decision_resume_frame_id": "turn:r3:p1",
            "decision_resume_module_id": "mod:trick",
            "decision_resume_module_type": "TrickWindowModule",
            "decision_resume_module_cursor": "await_trick_prompt",
        }
        resume = RuntimeDecisionResume(
            request_id="req_current_opaque",
            player_id=1,
            request_type="trick_tile_target",
            choice_id="4",
            choice_payload={},
            resume_token="resume_19",
            frame_id="turn:r3:p1",
            module_id="mod:trick",
            module_type="TrickWindowModule",
            module_cursor="await_trick_prompt",
            prompt_instance_id=19,
        )

        self.assertEqual(runtime_prompt_sequence_seed(state, checkpoint, resume), 18)

    def test_seed_prefers_current_pending_prompt_over_prior_resume_debug(self) -> None:
        state = SimpleNamespace(
            prompt_sequence=19,
            pending_prompt_instance_id=19,
            pending_prompt_request_id="sess_1:r3:t9:p1:trick_tile_target:19",
        )
        checkpoint = {
            "decision_resume_request_id": "sess_1:r3:t9:p1:trick_tile_target:18",
            "decision_resume_request_type": "trick_tile_target",
            "decision_resume_player_id": 1,
            "decision_resume_frame_id": "turn:r3:p1",
            "decision_resume_module_id": "mod:trick",
            "decision_resume_module_type": "TrickWindowModule",
            "decision_resume_module_cursor": "await_trick_prompt",
        }
        resume = RuntimeDecisionResume(
            request_id="sess_1:r3:t9:p1:trick_tile_target:19",
            player_id=1,
            request_type="trick_tile_target",
            choice_id="4",
            choice_payload={},
            resume_token="resume_19",
            frame_id="turn:r3:p1",
            module_id="mod:trick",
            module_type="TrickWindowModule",
            module_cursor="await_trick_prompt",
        )

        self.assertEqual(runtime_prompt_sequence_seed(state, checkpoint, resume), 18)


if __name__ == "__main__":
    unittest.main()
