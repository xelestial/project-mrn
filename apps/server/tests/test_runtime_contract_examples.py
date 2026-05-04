from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_type(value: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _validate_subset(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema:
        assert instance == schema["const"], f"{path}: expected const={schema['const']!r}, got {instance!r}"

    if "enum" in schema:
        assert instance in schema["enum"], f"{path}: expected enum in {schema['enum']!r}, got {instance!r}"

    if "type" in schema:
        schema_type = schema["type"]
        if isinstance(schema_type, list):
            assert any(_is_type(instance, t) for t in schema_type), (
                f"{path}: expected one of types {schema_type!r}, got {type(instance).__name__}"
            )
        else:
            assert _is_type(instance, schema_type), f"{path}: expected type={schema_type!r}, got {type(instance).__name__}"

    if isinstance(instance, str):
        if "minLength" in schema:
            assert len(instance) >= int(schema["minLength"]), (
                f"{path}: expected minLength>={schema['minLength']}, got {len(instance)}"
            )

    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema:
            assert instance >= int(schema["minimum"]), f"{path}: expected minimum>={schema['minimum']}, got {instance}"

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            assert key in instance, f"{path}: missing required key {key!r}"

        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, sub_schema in properties.items():
                if key in instance and isinstance(sub_schema, dict):
                    _validate_subset(instance[key], sub_schema, f"{path}.{key}")

    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(instance):
                _validate_subset(item, item_schema, f"{path}[{idx}]")


class RuntimeContractExampleTests(unittest.TestCase):
    def test_ws_examples_match_frozen_schemas(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schemas = root / "schemas"
        examples = root / "examples"

        pairs = [
            ("inbound.event.schema.json", "inbound.event.parameter_manifest.json"),
            ("inbound.event.schema.json", "inbound.event.decision_requested.external_ai.json"),
            ("inbound.prompt.schema.json", "inbound.prompt.movement.json"),
            ("inbound.decision_ack.schema.json", "inbound.decision_ack.accepted.json"),
            ("inbound.error.schema.json", "inbound.error.resume_gap_too_old.json"),
            ("inbound.heartbeat.schema.json", "inbound.heartbeat.backpressure.json"),
            ("outbound.resume.schema.json", "outbound.resume.json"),
            ("outbound.decision.schema.json", "outbound.decision.movement_roll.json"),
        ]

        for schema_name, example_name in pairs:
            schema = _load_json(schemas / schema_name)
            example = _load_json(examples / example_name)
            _validate_subset(example, schema, path=f"$<{example_name}>")

    def test_ws_decision_event_sequences_validate_and_keep_order(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        event_schema = _load_json(root / "schemas" / "inbound.event.schema.json")

        sequence_specs: list[tuple[str, list[str]]] = [
            (
                "sequence.decision.accepted_then_domain.json",
                ["decision_requested", "decision_resolved", "player_move"],
            ),
            (
                "sequence.decision.timeout_then_domain.json",
                ["decision_requested", "decision_resolved", "decision_timeout_fallback", "turn_end_snapshot"],
            ),
        ]

        for filename, expected_order in sequence_specs:
            sequence = _load_json(root / "examples" / filename)
            assert isinstance(sequence, list), f"{filename}: expected top-level array"
            assert len(sequence) >= len(expected_order), f"{filename}: expected at least {len(expected_order)} events"

            event_types: list[str] = []
            seqs: list[int] = []
            for idx, message in enumerate(sequence):
                assert isinstance(message, dict), f"{filename}[{idx}]: expected object message"
                _validate_subset(message, event_schema, path=f"$<{filename}>[{idx}]")
                payload = message.get("payload")
                assert isinstance(payload, dict), f"{filename}[{idx}].payload: expected object"
                event_type = payload.get("event_type")
                assert isinstance(event_type, str), f"{filename}[{idx}].payload.event_type: expected string"
                event_types.append(event_type)
                seq = message.get("seq")
                assert isinstance(seq, int), f"{filename}[{idx}].seq: expected integer"
                seqs.append(seq)

            assert seqs == sorted(seqs), f"{filename}: expected non-decreasing seq ordering"
            assert event_types == expected_order, (
                f"{filename}: expected event order {expected_order!r}, got {event_types!r}"
            )

    def test_selector_scene_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.scene.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.scene.turn_resolution.json")
        _validate_subset(example, schema, path="$<selector.scene.turn_resolution.json>")

    def test_selector_player_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.player.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.player.mark_target_visibility.json")
        _validate_subset(example, schema, path="$<selector.player.mark_target_visibility.json>")

    def test_selector_board_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.board.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.board.live_tiles.json")
        _validate_subset(example, schema, path="$<selector.board.live_tiles.json>")

    def test_selector_prompt_lap_reward_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.lap_reward_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.lap_reward_surface.json>")

    def test_selector_prompt_burden_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.burden_exchange_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.burden_exchange_surface.json>")

    def test_selector_prompt_mark_target_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.mark_target_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.mark_target_surface.json>")

    def test_selector_prompt_active_flip_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.active_flip_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.active_flip_surface.json>")

    def test_selector_prompt_coin_placement_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.coin_placement_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.coin_placement_surface.json>")

    def test_selector_prompt_movement_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.movement_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.movement_surface.json>")

    def test_selector_prompt_hand_choice_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.hand_choice_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.hand_choice_surface.json>")

    def test_selector_prompt_runaway_step_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.runaway_step_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.runaway_step_surface.json>")

    def test_selector_prompt_geo_bonus_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.geo_bonus_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.geo_bonus_surface.json>")

    def test_selector_prompt_pabal_dice_mode_fixture_matches_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        example = _load_json(root / "examples" / "selector.prompt.pabal_dice_mode_surface.json")
        _validate_subset(example, schema, path="$<selector.prompt.pabal_dice_mode_surface.json>")

    def test_all_selector_prompt_surface_fixtures_match_shared_schema(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "ws"
        schema = _load_json(root / "schemas" / "selector.prompt.fixture.schema.json")
        examples = root / "examples"

        for example_path in sorted(examples.glob("selector.prompt.*_surface.json")):
            example = _load_json(example_path)
            _validate_subset(example, schema, path=f"$<{example_path.name}>")

    def test_external_ai_examples_match_frozen_schemas(self) -> None:
        root = _project_root() / "packages" / "runtime-contracts" / "external-ai"
        schemas = root / "schemas"
        examples = root / "examples"

        pairs = [
            ("request.schema.json", "request.purchase_tile.json"),
            ("request.schema.json", "request.movement.json"),
            ("request.schema.json", "request.lap_reward.json"),
            ("request.schema.json", "request.mark_target.json"),
            ("request.schema.json", "request.active_flip.json"),
            ("response.schema.json", "response.purchase_tile_yes.json"),
            ("response.schema.json", "response.movement_dice.json"),
            ("response.schema.json", "response.lap_reward_cash.json"),
            ("response.schema.json", "response.mark_target_p1.json"),
            ("response.schema.json", "response.active_flip_card_7.json"),
        ]

        for schema_name, example_name in pairs:
            schema = _load_json(schemas / schema_name)
            example = _load_json(examples / example_name)
            _validate_subset(example, schema, path=f"$<{example_name}>")


if __name__ == "__main__":
    unittest.main()
