from __future__ import annotations

from typing import Callable

from apps.server.src.domain.protocol_ids import prompt_protocol_identity_fields
from apps.server.src.domain.prompt_sequence import PromptInstanceSequencer, prepare_prompt_boundary_envelope


class PromptBoundaryBuilder:
    """Allocates prompt instances and builds the prompt boundary envelope."""

    def __init__(
        self,
        *,
        current_prompt_sequence: int = 0,
        stable_request_id_resolver: Callable[[dict, dict], str] | None = None,
        ensure_engine_import_path: Callable[[], None] | None = None,
    ) -> None:
        self._prompt_instances = PromptInstanceSequencer(current_prompt_sequence)
        self._stable_request_id_resolver = stable_request_id_resolver
        self._ensure_engine_import_path = ensure_engine_import_path or (lambda: None)

    def current_prompt_sequence(self) -> int:
        return self._prompt_instances.current

    def set_prompt_sequence(self, value: int) -> None:
        self._prompt_instances.set_current(value)

    def prepare(
        self,
        prompt: dict,
        *,
        active_call=None,  # noqa: ANN001
        replace_prompt_instance_id: bool = False,
    ) -> dict:
        prompt_instance_id = self._prompt_instances.allocate_next()
        envelope = prepare_prompt_boundary_envelope(
            prompt,
            prompt_instance_id=prompt_instance_id,
            active_call=active_call,
            replace_prompt_instance_id=replace_prompt_instance_id,
        )
        _attach_prompt_protocol_identity(envelope)
        if active_call is not None:
            attach_active_module_continuation_to_envelope(
                envelope,
                active_call,
                stable_request_id_resolver=self._stable_request_id_resolver,
                ensure_engine_import_path=self._ensure_engine_import_path,
            )
            _attach_prompt_protocol_identity(envelope)
        return envelope


def attach_active_module_continuation_to_envelope(
    envelope: dict,
    active_call,
    *,
    stable_request_id_resolver=None,
    ensure_engine_import_path: Callable[[], None] | None = None,
) -> None:  # noqa: ANN001
    invocation = getattr(active_call, "invocation", None)
    state = getattr(invocation, "state", None)
    if state is None or str(getattr(state, "runtime_runner_kind", "") or "").lower() != "module":
        return
    frame, module = _active_frame_and_module(state)
    if frame is None or module is None:
        return
    boundary_fields = {
        "runner_kind": "module",
        "frame_type": str(getattr(frame, "frame_type", "") or ""),
        "frame_id": str(getattr(frame, "frame_id", "") or ""),
        "module_id": str(getattr(module, "module_id", "") or ""),
        "module_type": str(getattr(module, "module_type", "") or ""),
        "module_cursor": str(getattr(module, "cursor", "") or ""),
        "idempotency_key": str(getattr(module, "idempotency_key", "") or ""),
    }
    envelope.update({key: value for key, value in boundary_fields.items() if value and key != "idempotency_key"})
    existing_runtime_module = envelope.get("runtime_module")
    if not isinstance(existing_runtime_module, dict):
        existing_runtime_module = {}
    envelope["runtime_module"] = {**boundary_fields, **existing_runtime_module}
    request = getattr(active_call, "request", None)
    request_type = str(envelope.get("request_type") or getattr(request, "request_type", "") or "")
    internal_player_id = getattr(request, "player_id", None)
    if internal_player_id is None:
        internal_player_id = int(envelope.get("player_id", 1) or 1) - 1
    public_context = dict(envelope.get("public_context") or {})
    existing_continuation = getattr(state, "runtime_active_prompt", None)
    if not str(envelope.get("request_id") or "").strip() and _is_matching_prompt_boundary(
        existing_continuation,
        frame_id=str(getattr(frame, "frame_id", "") or ""),
        module_id=str(getattr(module, "module_id", "") or ""),
        player_id=int(internal_player_id),
        request_type=request_type,
    ):
        envelope["request_id"] = str(getattr(existing_continuation, "request_id", "") or "")
    if not str(envelope.get("request_id") or "").strip() and callable(stable_request_id_resolver):
        envelope["request_id"] = str(stable_request_id_resolver(envelope, public_context))
    request_id = str(envelope.get("request_id") or "").strip()
    if not request_id:
        return
    legal_choices = envelope.get("legal_choices")
    if not isinstance(legal_choices, list):
        legal_choices = list(getattr(active_call, "legal_choices", []) or [])
        envelope["legal_choices"] = legal_choices
    if ensure_engine_import_path is not None:
        ensure_engine_import_path()
    from runtime_modules.prompts import PromptApi

    if _is_matching_prompt_continuation(
        existing_continuation,
        request_id=request_id,
        frame_id=str(getattr(frame, "frame_id", "") or ""),
        module_id=str(getattr(module, "module_id", "") or ""),
        player_id=int(internal_player_id),
        request_type=request_type,
    ):
        continuation = existing_continuation
    else:
        continuation = PromptApi().create_continuation(
            request_id=request_id,
            prompt_instance_id=int(envelope.get("prompt_instance_id", 0) or 0),
            frame=frame,
            module=module,
            player_id=int(internal_player_id),
            request_type=request_type,
            legal_choices=[dict(choice) for choice in legal_choices if isinstance(choice, dict)],
            public_context=public_context,
        )
    state.runtime_active_prompt = continuation
    state.runtime_active_prompt_batch = None
    module_fields = {
        "runner_kind": "module",
        "frame_type": str(getattr(frame, "frame_type", "") or ""),
        "frame_id": continuation.frame_id,
        "module_id": continuation.module_id,
        "module_type": continuation.module_type,
        "module_cursor": continuation.module_cursor,
        "idempotency_key": str(getattr(module, "idempotency_key", "") or ""),
    }
    envelope.update(
        {
            "runner_kind": "module",
            "resume_token": continuation.resume_token,
            "frame_id": continuation.frame_id,
            "module_id": continuation.module_id,
            "module_type": continuation.module_type,
            "module_cursor": continuation.module_cursor,
            "runtime_module": module_fields,
        }
    )


def _is_matching_prompt_continuation(
    continuation,
    *,
    request_id: str,
    frame_id: str,
    module_id: str,
    player_id: int,
    request_type: str,
) -> bool:  # noqa: ANN001
    if continuation is None:
        return False
    continuation_player_id = getattr(continuation, "player_id", None)
    if continuation_player_id is None:
        return False
    return (
        str(getattr(continuation, "request_id", "") or "") == request_id
        and str(getattr(continuation, "frame_id", "") or "") == frame_id
        and str(getattr(continuation, "module_id", "") or "") == module_id
        and int(continuation_player_id) == int(player_id)
        and str(getattr(continuation, "request_type", "") or "") == request_type
    )


def _is_matching_prompt_boundary(
    continuation,
    *,
    frame_id: str,
    module_id: str,
    player_id: int,
    request_type: str,
) -> bool:  # noqa: ANN001
    if continuation is None:
        return False
    continuation_player_id = getattr(continuation, "player_id", None)
    if continuation_player_id is None:
        return False
    return (
        str(getattr(continuation, "frame_id", "") or "") == frame_id
        and str(getattr(continuation, "module_id", "") or "") == module_id
        and int(continuation_player_id) == int(player_id)
        and str(getattr(continuation, "request_type", "") or "") == request_type
    )


def _active_frame_and_module(state) -> tuple[object | None, object | None]:  # noqa: ANN001
    frames = getattr(state, "runtime_frame_stack", None)
    if not isinstance(frames, list):
        return None, None
    for frame in reversed(frames):
        active_module_id = getattr(frame, "active_module_id", None)
        if not active_module_id:
            continue
        for module in getattr(frame, "module_queue", []) or []:
            if getattr(module, "module_id", None) == active_module_id:
                return frame, module
    return None, None


def _attach_prompt_protocol_identity(envelope: dict) -> None:
    request_id = str(envelope.get("request_id") or "").strip()
    if not request_id:
        return
    identity_source = str(envelope.get("legacy_request_id") or request_id).strip()
    if _looks_like_public_request_id(request_id):
        envelope.setdefault("public_request_id", request_id)
        envelope.setdefault("legacy_request_id", identity_source)
        for key, value in prompt_protocol_identity_fields(
            request_id=identity_source,
            prompt_instance_id=envelope.get("prompt_instance_id"),
        ).items():
            if key != "public_request_id":
                envelope.setdefault(key, value)
        return
    for key, value in prompt_protocol_identity_fields(
        request_id=identity_source,
        prompt_instance_id=envelope.get("prompt_instance_id"),
    ).items():
        envelope.setdefault(key, value)


def _looks_like_public_request_id(request_id: str) -> bool:
    return str(request_id or "").strip().startswith("req_")


__all__ = ["PromptBoundaryBuilder", "attach_active_module_continuation_to_envelope"]
