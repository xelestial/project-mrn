from __future__ import annotations

import ast
from pathlib import Path

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = PROJECT_ROOT / "engine"


ENGINE_DECISION_CONTINUATION_CLASSIFICATION: dict[str, str] = {
    "choose_active_flip_card": "atomic_effect_boundary",
    "choose_burden_exchange_on_supply": "simultaneous_prompt_batch_boundary",
    "choose_coin_placement_tile": "queued_action_boundary",
    "choose_dice_card_value": "atomic_effect_boundary",
    "choose_doctrine_relief_target": "atomic_effect_boundary",
    "choose_draft_card": "round_setup_boundary",
    "choose_final_character": "round_setup_boundary",
    "choose_lap_reward": "atomic_effect_boundary",
    "choose_mark_target": "atomic_effect_boundary",
    "choose_movement": "turn_boundary",
    "choose_purchase_tile": "queued_action_boundary",
    "choose_runaway_slave_step": "turn_boundary",
    "choose_specific_trick_reward": "atomic_effect_boundary",
    "choose_trick_redraw_card": "atomic_effect_boundary",
    "choose_trick_tile_target": "queued_action_boundary",
    "choose_trick_to_use": "turn_boundary",
}

ENGINE_DECISION_CONTINUATION_CATEGORIES = {
    "turn_boundary",
    "round_setup_boundary",
    "queued_action_boundary",
    "atomic_effect_boundary",
    "simultaneous_prompt_batch_boundary",
    "immediate_helper_boundary",
}

ENGINE_IMMEDIATE_HELPER_ALLOWED_CALLERS: dict[str, set[str]] = {
    "_advance_player": set(),
    "_apply_fortune_arrival": {"_apply_fortune_card_impl"},
    "_apply_fortune_move_only": {"_apply_fortune_card_impl"},
}


def _production_python_files() -> list[Path]:
    return [
        path
        for path in ENGINE_ROOT.rglob("*.py")
        if not path.name.startswith("test_")
        and "__pycache__" not in path.parts
    ]


def test_production_effects_do_not_call_immediate_movement_helpers() -> None:
    disallowed = {
        "._advance_player(",
        "._apply_fortune_arrival(",
        "._apply_fortune_move_only(",
    }
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "engine.py":
            continue
        source = path.read_text(encoding="utf-8")
        for token in disallowed:
            if token in source:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} uses {token}")

    assert offenders == []


def test_engine_immediate_movement_helpers_are_limited_to_allowed_callers() -> None:
    source = (ENGINE_ROOT / "engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []

    class ImmediateHelperVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._function_stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._function_stack.append(node.name)
            self.generic_visit(node)
            self._function_stack.pop()

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Attribute):
                helper_name = node.func.attr
                if helper_name in ENGINE_IMMEDIATE_HELPER_ALLOWED_CALLERS:
                    caller = self._function_stack[-1] if self._function_stack else "<module>"
                    allowed_callers = ENGINE_IMMEDIATE_HELPER_ALLOWED_CALLERS[helper_name]
                    if caller not in allowed_callers:
                        offenders.append(f"{helper_name} called by {caller} at line {node.lineno}")
            self.generic_visit(node)

    ImmediateHelperVisitor().visit(tree)

    assert offenders == []


def test_landing_effect_handlers_do_not_open_purchase_or_token_prompts_inline() -> None:
    source = (ENGINE_ROOT / "effect_handlers.py").read_text(encoding="utf-8")
    disallowed = {
        '_request_decision("choose_purchase_tile"',
        "_request_decision('choose_purchase_tile'",
        '_request_decision("choose_coin_placement_tile"',
        "_request_decision('choose_coin_placement_tile'",
        '_request_decision("choose_trick_tile_target"',
        "_request_decision('choose_trick_tile_target'",
    }
    offenders = [token for token in disallowed if token in source]

    assert offenders == []


def test_request_decisions_are_classified_for_redis_continuation() -> None:
    found: set[str] = set()
    dynamic_call_lines: list[str] = []
    for path in _production_python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_request_decision"
            ):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)
            else:
                dynamic_call_lines.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    missing = sorted(found - set(ENGINE_DECISION_CONTINUATION_CLASSIFICATION))
    stale = sorted(set(ENGINE_DECISION_CONTINUATION_CLASSIFICATION) - found)
    invalid_categories = {
        name: category
        for name, category in ENGINE_DECISION_CONTINUATION_CLASSIFICATION.items()
        if category not in ENGINE_DECISION_CONTINUATION_CATEGORIES
    }

    assert dynamic_call_lines == []
    assert missing == []
    assert stale == []
    assert invalid_categories == {}


def test_burden_exchange_supply_is_simultaneous_prompt_batch_boundary() -> None:
    assert (
        ENGINE_DECISION_CONTINUATION_CLASSIFICATION["choose_burden_exchange_on_supply"]
        == "simultaneous_prompt_batch_boundary"
    )
