from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[4] / "packages" / "ui-domain" / "gameplay_catalog.json"


@lru_cache(maxsize=1)
def load_gameplay_catalog() -> dict[str, Any]:
    return json.loads(_catalog_path().read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _slot_by_alias() -> dict[str, int]:
    mapping: dict[str, int] = {}
    for slot in load_gameplay_catalog()["character_slots"]:
        slot_no = int(slot["slot"])
        for face in slot["faces"]:
            name = str(face["name"]).strip()
            if name:
                mapping[name] = slot_no
            for alias in face.get("aliases", []):
                normalized = str(alias).strip()
                if normalized:
                    mapping[normalized] = slot_no
    return mapping


@lru_cache(maxsize=1)
def _faces_by_slot() -> dict[int, tuple[str, str]]:
    mapping: dict[int, tuple[str, str]] = {}
    for slot in load_gameplay_catalog()["character_slots"]:
        faces = slot["faces"]
        mapping[int(slot["slot"])] = (str(faces[0]["name"]), str(faces[1]["name"]))
    return mapping


def priority_slot_for_character_name(character: str | None) -> int | None:
    if not isinstance(character, str):
        return None
    normalized = character.strip()
    if not normalized:
        return None
    return _slot_by_alias().get(normalized)


def characters_for_slot(slot: int) -> tuple[str, str] | None:
    return _faces_by_slot().get(slot)


def opposite_character_name_for_slot(slot: int, active_character: str | None) -> str | None:
    pair = characters_for_slot(slot)
    if pair is None:
        return None
    normalized = active_character.strip() if isinstance(active_character, str) else ""
    if not normalized:
        return pair[1]
    if pair[0] == normalized:
        return pair[1]
    if pair[1] == normalized:
        return pair[0]
    return pair[1]
