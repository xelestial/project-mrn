from __future__ import annotations


def _request_prompt_instance_id(request_id: str, request_type: str) -> int:
    request_id = str(request_id or "").strip()
    request_type = str(request_type or "").strip()
    if not request_type or not request_id:
        return 0
    marker = f":{request_type}:"
    if marker not in request_id:
        return 0
    raw_instance_id = request_id.rsplit(marker, 1)[-1]
    try:
        return max(0, int(raw_instance_id))
    except (TypeError, ValueError):
        return 0


def _positive_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _resume_prompt_instance_id(resume: object | None) -> int:
    if resume is None:
        return 0
    explicit = _positive_int(getattr(resume, "prompt_instance_id", 0))
    if explicit > 0:
        return explicit
    return _request_prompt_instance_id(
        str(getattr(resume, "request_id", "") or ""),
        str(getattr(resume, "request_type", "") or ""),
    )


def _prior_same_module_resume_prompt_seed(checkpoint: dict | None, resume: object | None) -> int | None:
    if not isinstance(checkpoint, dict) or resume is None:
        return None
    previous_request_id = str(checkpoint.get("decision_resume_request_id") or "").strip()
    if not previous_request_id or previous_request_id == str(getattr(resume, "request_id", "") or "").strip():
        return None
    previous_request_type = str(checkpoint.get("decision_resume_request_type") or "").strip()
    if previous_request_type and previous_request_type != str(getattr(resume, "request_type", "") or "").strip():
        return None
    previous_player_id = checkpoint.get("decision_resume_player_id")
    if previous_player_id not in (None, ""):
        try:
            if int(previous_player_id) != int(getattr(resume, "player_id")):
                return None
        except (TypeError, ValueError):
            return None
    identity_fields = (
        ("decision_resume_frame_id", "frame_id"),
        ("decision_resume_module_id", "module_id"),
        ("decision_resume_module_type", "module_type"),
        ("decision_resume_module_cursor", "module_cursor"),
    )
    for checkpoint_field, resume_field in identity_fields:
        checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
        resume_value = str(getattr(resume, resume_field, "") or "").strip()
        if checkpoint_value and resume_value and checkpoint_value != resume_value:
            return None
    request_type = previous_request_type or str(getattr(resume, "request_type", "") or "").strip()
    previous_instance_id = _positive_int(checkpoint.get("decision_resume_prompt_instance_id"))
    if previous_instance_id <= 0:
        previous_instance_id = _request_prompt_instance_id(previous_request_id, request_type)
    current_instance_id = _resume_prompt_instance_id(resume)
    if previous_instance_id <= 0 or current_instance_id <= previous_instance_id:
        return None
    return max(0, previous_instance_id - 1)


def runtime_prompt_sequence_seed(
    state: object,
    checkpoint: dict | None,
    decision_resume: object | None,
) -> int:
    prompt_sequence = int(getattr(state, "prompt_sequence", 0) or 0)
    pending_prompt_instance_id = int(getattr(state, "pending_prompt_instance_id", 0) or 0)
    pending_prompt_request_id = str(getattr(state, "pending_prompt_request_id", "") or "").strip()
    resume_request_id = str(getattr(decision_resume, "request_id", "") or "").strip() if decision_resume is not None else ""
    resume_prompt_instance_id = _resume_prompt_instance_id(decision_resume)
    pending_prompt_matches_resume = (
        decision_resume is not None
        and pending_prompt_request_id
        and pending_prompt_request_id == resume_request_id
        and pending_prompt_instance_id == resume_prompt_instance_id
    )
    prior_prompt_seed = _prior_same_module_resume_prompt_seed(checkpoint, decision_resume)
    if pending_prompt_instance_id > 0 and (
        decision_resume is None
        or pending_prompt_matches_resume
    ):
        if pending_prompt_matches_resume and prior_prompt_seed is not None and resume_prompt_instance_id > prior_prompt_seed + 2:
            return prior_prompt_seed
        return max(0, pending_prompt_instance_id - 1)

    if prior_prompt_seed is not None:
        return prior_prompt_seed
    return prompt_sequence


__all__ = ["runtime_prompt_sequence_seed"]
