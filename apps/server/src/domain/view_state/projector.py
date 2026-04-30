from __future__ import annotations

from apps.server.src.domain.visibility import ViewerContext, project_stream_message_for_viewer

from .board_selector import build_board_view_state
from .hand_selector import build_hand_tray_view_state
from .player_selector import build_active_slots_view_state, build_mark_target_view_state, build_player_view_state
from .prompt_selector import build_prompt_view_state
from .reveal_selector import build_reveals_view_state
from .scene_selector import build_scene_view_state
from .turn_selector import build_turn_stage_view_state
from .types import ViewStatePayload


def project_view_state(messages: list[dict], viewer: ViewerContext | None = None) -> ViewStatePayload:
    if viewer is not None:
        messages = _messages_for_viewer(messages, viewer)
    payload: ViewStatePayload = {}
    players = build_player_view_state(messages)
    if players:
        payload["players"] = players
    active_slots = build_active_slots_view_state(messages)
    if active_slots:
        payload["active_slots"] = active_slots
    mark_target = build_mark_target_view_state(messages)
    if mark_target:
        payload["mark_target"] = mark_target
    reveals = build_reveals_view_state(messages)
    if reveals:
        payload["reveals"] = reveals
    board = build_board_view_state(messages)
    if board:
        payload["board"] = board
    prompt = build_prompt_view_state(messages)
    if prompt:
        payload["prompt"] = prompt
    hand_tray = build_hand_tray_view_state(messages)
    if hand_tray:
        payload["hand_tray"] = hand_tray
    turn_stage = build_turn_stage_view_state(messages)
    if turn_stage:
        payload["turn_stage"] = turn_stage
    scene = build_scene_view_state(messages)
    if scene:
        payload["scene"] = scene
    return payload


def _messages_for_viewer(messages: list[dict], viewer: ViewerContext) -> list[dict]:
    projected: list[dict] = []
    for message in messages:
        item = project_stream_message_for_viewer(message, viewer)
        if item is not None:
            projected.append(item)
    return projected
