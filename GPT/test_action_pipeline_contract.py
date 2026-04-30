from __future__ import annotations

from pathlib import Path

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GPT_ROOT = PROJECT_ROOT / "GPT"


def _production_python_files() -> list[Path]:
    return [
        path
        for path in GPT_ROOT.rglob("*.py")
        if not path.name.startswith("test_")
        and "__pycache__" not in path.parts
    ]


def test_production_effects_do_not_call_immediate_movement_compat_helpers() -> None:
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


def test_landing_effect_handlers_do_not_open_purchase_or_token_prompts_inline() -> None:
    source = (GPT_ROOT / "effect_handlers.py").read_text(encoding="utf-8")
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
