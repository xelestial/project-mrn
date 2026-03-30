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


if __name__ == "__main__":
    unittest.main()

