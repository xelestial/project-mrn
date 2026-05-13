from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.server.src.domain.prompt_sequence import (
    PromptInstanceSequencer,
    clear_prompt_boundary_state,
    prepare_prompt_boundary_envelope,
    prompt_instance_id_from_resume,
    prompt_resume_matches_next_instance,
    prompt_sequence_after_resume,
    record_prompt_boundary_state,
    runtime_prompt_sequence_seed,
)
from apps.server.src.services.runtime_service import RuntimeDecisionResume


class PromptSequenceTests(unittest.TestCase):
    def test_prompt_instance_sequencer_resumes_and_allocates_next_instance(self) -> None:
        sequencer = PromptInstanceSequencer()

        sequencer.set_current(4)

        self.assertEqual(sequencer.current, 4)
        self.assertEqual(sequencer.allocate_next(), 5)
        self.assertEqual(sequencer.current, 5)

    def test_prompt_instance_sequencer_clamps_invalid_seed_to_zero(self) -> None:
        sequencer = PromptInstanceSequencer()

        sequencer.set_current(-7)

        self.assertEqual(sequencer.current, 0)
        self.assertEqual(sequencer.allocate_next(), 1)

    def test_prompt_resume_matches_when_instance_is_unknown_or_sequence_unseeded(self) -> None:
        self.assertTrue(prompt_resume_matches_next_instance(current_prompt_sequence=4, resume_prompt_instance_id=0))
        self.assertTrue(prompt_resume_matches_next_instance(current_prompt_sequence=0, resume_prompt_instance_id=7))

    def test_prompt_resume_matches_only_next_seeded_instance(self) -> None:
        self.assertTrue(prompt_resume_matches_next_instance(current_prompt_sequence=4, resume_prompt_instance_id=5))
        self.assertFalse(prompt_resume_matches_next_instance(current_prompt_sequence=4, resume_prompt_instance_id=6))

    def test_prompt_sequence_after_resume_advances_by_current_or_explicit_resume_instance(self) -> None:
        self.assertEqual(prompt_sequence_after_resume(current_prompt_sequence=4, resume_prompt_instance_id=0), 5)
        self.assertEqual(prompt_sequence_after_resume(current_prompt_sequence=4, resume_prompt_instance_id=7), 7)

    def test_prompt_instance_id_from_resume_uses_explicit_field_only(self) -> None:
        explicit_resume = SimpleNamespace(
            request_id="opaque",
            prompt_instance_id=9,
        )
        legacy_shape_resume = SimpleNamespace(
            request_id="sess_1:r3:t9:p1:trick_tile_target:60",
        )

        self.assertEqual(prompt_instance_id_from_resume(explicit_resume), 9)
        self.assertEqual(prompt_instance_id_from_resume(legacy_shape_resume), 0)

    def test_prepare_prompt_boundary_envelope_adds_instance_without_mutating_prompt(self) -> None:
        prompt = {"request_type": "movement", "public_context": {"source": "prompt"}}

        envelope = prepare_prompt_boundary_envelope(prompt, prompt_instance_id=3)

        self.assertEqual(envelope["prompt_instance_id"], 3)
        self.assertEqual(envelope["request_type"], "movement")
        self.assertNotIn("prompt_instance_id", prompt)

    def test_prepare_prompt_boundary_envelope_can_replace_existing_instance(self) -> None:
        prompt = {"prompt_instance_id": 2}

        envelope = prepare_prompt_boundary_envelope(
            prompt,
            prompt_instance_id=4,
            replace_prompt_instance_id=True,
        )

        self.assertEqual(envelope["prompt_instance_id"], 4)
        self.assertEqual(prompt["prompt_instance_id"], 2)

    def test_prepare_prompt_boundary_envelope_merges_active_request_metadata(self) -> None:
        prompt = {"public_context": {"source": "prompt", "shared": "prompt_value"}}
        active_call = SimpleNamespace(
            request=SimpleNamespace(
                request_type="trick_tile_target",
                player_id=1,
                fallback_policy="required",
                public_context={"shared": "request_value", "frame_id": "turn:r2:p1"},
            )
        )

        envelope = prepare_prompt_boundary_envelope(prompt, prompt_instance_id=8, active_call=active_call)

        self.assertEqual(envelope["prompt_instance_id"], 8)
        self.assertEqual(envelope["request_type"], "trick_tile_target")
        self.assertEqual(envelope["player_id"], 2)
        self.assertEqual(envelope["fallback_policy"], "required")
        self.assertEqual(
            envelope["public_context"],
            {"source": "prompt", "shared": "request_value", "frame_id": "turn:r2:p1"},
        )

    def test_record_prompt_boundary_state_tracks_pending_prompt_and_sequence(self) -> None:
        state = SimpleNamespace(prompt_sequence=4)

        record_prompt_boundary_state(
            state,
            {
                "request_id": "req_5",
                "request_type": "movement",
                "player_id": 2,
                "prompt_instance_id": 5,
            },
        )

        self.assertEqual(state.prompt_sequence, 5)
        self.assertEqual(state.pending_prompt_request_id, "req_5")
        self.assertEqual(state.pending_prompt_type, "movement")
        self.assertEqual(state.pending_prompt_player_id, 2)
        self.assertEqual(state.pending_prompt_instance_id, 5)

    def test_record_prompt_boundary_state_preserves_higher_prompt_sequence(self) -> None:
        state = SimpleNamespace(prompt_sequence=7)

        record_prompt_boundary_state(
            state,
            {
                "request_id": "req_5",
                "request_type": "movement",
                "player_id": 2,
                "prompt_instance_id": 5,
            },
        )

        self.assertEqual(state.prompt_sequence, 7)
        self.assertEqual(state.pending_prompt_instance_id, 5)

    def test_clear_prompt_boundary_state_resets_pending_prompt_fields(self) -> None:
        state = SimpleNamespace(
            pending_prompt_request_id="req_5",
            pending_prompt_type="movement",
            pending_prompt_player_id=2,
            pending_prompt_instance_id=5,
        )

        clear_prompt_boundary_state(state)

        self.assertEqual(state.pending_prompt_request_id, "")
        self.assertEqual(state.pending_prompt_type, "")
        self.assertEqual(state.pending_prompt_player_id, 0)
        self.assertEqual(state.pending_prompt_instance_id, 0)

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

    def test_seed_prefers_current_pending_prompt_over_explicit_prior_resume_debug(self) -> None:
        state = SimpleNamespace(
            prompt_sequence=19,
            pending_prompt_instance_id=19,
            pending_prompt_request_id="sess_1:r3:t9:p1:trick_tile_target:19",
        )
        checkpoint = {
            "decision_resume_request_id": "sess_1:r3:t9:p1:trick_tile_target:18",
            "decision_resume_request_type": "trick_tile_target",
            "decision_resume_player_id": 1,
            "decision_resume_prompt_instance_id": 18,
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
            prompt_instance_id=19,
        )

        self.assertEqual(runtime_prompt_sequence_seed(state, checkpoint, resume), 18)

    def test_seed_does_not_parse_legacy_request_id_without_explicit_prompt_instance(self) -> None:
        state = SimpleNamespace(
            prompt_sequence=19,
            pending_prompt_instance_id=0,
            pending_prompt_request_id="",
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

        self.assertEqual(runtime_prompt_sequence_seed(state, checkpoint, resume), 19)


if __name__ == "__main__":
    unittest.main()
