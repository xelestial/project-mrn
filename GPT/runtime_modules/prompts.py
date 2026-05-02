from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from .contracts import FrameState, ModuleRef, PromptContinuation, SimultaneousPromptBatchContinuation


class PromptContinuationError(ValueError):
    pass


@dataclass(slots=True)
class PromptApi:
    def create_continuation(
        self,
        *,
        request_id: str,
        prompt_instance_id: int,
        frame: FrameState,
        module: ModuleRef,
        player_id: int,
        request_type: str,
        legal_choices: list[dict[str, Any]],
        public_context: dict[str, Any] | None = None,
        expires_at_ms: int | None = None,
    ) -> PromptContinuation:
        return PromptContinuation(
            request_id=request_id,
            prompt_instance_id=prompt_instance_id,
            resume_token=f"resume_{secrets.token_hex(16)}",
            frame_id=frame.frame_id,
            module_id=module.module_id,
            module_type=module.module_type,
            player_id=player_id,
            request_type=request_type,
            legal_choices=list(legal_choices),
            public_context=dict(public_context or {}),
            expires_at_ms=expires_at_ms,
        )

    def create_batch(
        self,
        *,
        batch_id: str,
        frame: FrameState,
        module: ModuleRef,
        participant_player_ids: list[int],
        request_type: str,
        legal_choices_by_player_id: dict[int, list[dict[str, Any]]],
        public_context_by_player_id: dict[int, dict[str, Any]] | None = None,
        eligibility_snapshot: dict[str, Any] | None = None,
        commit_policy: str = "all_required",
        default_policy: dict[str, Any] | None = None,
        expires_at_ms: int | None = None,
    ) -> SimultaneousPromptBatchContinuation:
        prompts: dict[int, PromptContinuation] = {}
        contexts = dict(public_context_by_player_id or {})
        for player_id in participant_player_ids:
            prompts[int(player_id)] = self.create_continuation(
                request_id=f"{batch_id}:p{int(player_id)}",
                prompt_instance_id=0,
                frame=frame,
                module=module,
                player_id=int(player_id),
                request_type=request_type,
                legal_choices=legal_choices_by_player_id.get(int(player_id), []),
                public_context=contexts.get(int(player_id), {}),
                expires_at_ms=expires_at_ms,
            )
        return SimultaneousPromptBatchContinuation(
            batch_id=batch_id,
            frame_id=frame.frame_id,
            module_id=module.module_id,
            module_type=module.module_type,
            request_type=request_type,
            participant_player_ids=[int(player_id) for player_id in participant_player_ids],
            prompts_by_player_id=prompts,
            missing_player_ids=[int(player_id) for player_id in participant_player_ids],
            eligibility_snapshot=dict(eligibility_snapshot or {}),
            commit_policy="timeout_default" if commit_policy == "timeout_default" else "all_required",
            default_policy=dict(default_policy or {}),
            expires_at_ms=expires_at_ms,
        )

    def record_batch_response(
        self,
        batch: SimultaneousPromptBatchContinuation,
        *,
        player_id: int,
        request_id: str,
        resume_token: str,
        choice_id: str,
        response: dict[str, Any] | None = None,
    ) -> bool:
        player_id = int(player_id)
        continuation = batch.prompts_by_player_id.get(player_id)
        if continuation is None or player_id not in batch.participant_player_ids:
            raise PromptContinuationError("player is not part of this prompt batch")
        validate_resume(
            continuation,
            request_id=request_id,
            resume_token=resume_token,
            frame_id=batch.frame_id,
            module_id=batch.module_id,
            player_id=player_id,
            choice_id=choice_id,
        )
        if player_id in batch.responses_by_player_id:
            previous_choice = str(batch.responses_by_player_id[player_id].get("choice_id") or "")
            if previous_choice != choice_id:
                raise PromptContinuationError("player already responded to this batch")
            return not batch.missing_player_ids
        batch.responses_by_player_id[player_id] = {"choice_id": choice_id, **dict(response or {})}
        batch.missing_player_ids = [
            participant_id for participant_id in batch.participant_player_ids
            if participant_id not in batch.responses_by_player_id
        ]
        return not batch.missing_player_ids


def validate_resume(
    continuation: PromptContinuation | None,
    *,
    request_id: str,
    resume_token: str,
    frame_id: str,
    module_id: str,
    player_id: int,
    choice_id: str,
) -> None:
    if continuation is None:
        raise PromptContinuationError("no active prompt continuation")
    if continuation.request_id != request_id:
        raise PromptContinuationError("request id mismatch")
    if continuation.resume_token != resume_token:
        raise PromptContinuationError("resume token mismatch")
    if continuation.frame_id != frame_id:
        raise PromptContinuationError("frame id mismatch")
    if continuation.module_id != module_id:
        raise PromptContinuationError("module id mismatch")
    if continuation.player_id != player_id:
        raise PromptContinuationError("player mismatch")
    legal = {str(choice.get("choice_id") or "") for choice in continuation.legal_choices}
    if choice_id not in legal:
        raise PromptContinuationError("choice is not legal")
