from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True, slots=True)
class TrickCardDef:
    copies: int
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class TrickCard:
    deck_index: int
    name: str
    description: str

    @property
    def is_burden(self) -> bool:
        return self.name in {"무거운 짐", "가벼운 짐"}

    @property
    def is_anytime(self) -> bool:
        return "언제나 사용할 수 있습니다" in self.description

    @property
    def burden_cost(self) -> int:
        if self.name == "무거운 짐":
            return 4
        if self.name == "가벼운 짐":
            return 2
        return 0


def _default_csv_path() -> Path:
    return Path(__file__).with_name("trick.csv")


def _resolve_csv_path(csv_path: str | Path | None = None) -> Path:
    path = Path(csv_path) if csv_path is not None else _default_csv_path()
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).with_name(str(path))
    return path.resolve()


@lru_cache(maxsize=None)
def _load_trick_definitions_cached(csv_path_str: str) -> Tuple[TrickCardDef, ...]:
    path = Path(csv_path_str)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        defs: list[TrickCardDef] = []
        for row in reader:
            raw_copies = (row.get("전체 장수") or "").strip()
            raw_name = " ".join((row.get("이름") or "").split())
            raw_desc = (row.get("설명") or "").strip()
            if not raw_copies or not raw_name or not raw_desc:
                continue
            defs.append(TrickCardDef(copies=int(raw_copies), name=raw_name, description=raw_desc))
        return tuple(defs)


def load_trick_definitions(csv_path: str | Path | None = None) -> list[TrickCardDef]:
    return list(_load_trick_definitions_cached(str(_resolve_csv_path(csv_path))))


@lru_cache(maxsize=None)
def _build_trick_deck_cached(csv_path_str: str) -> Tuple[TrickCard, ...]:
    deck: list[TrickCard] = []
    deck_index = 1
    for card_def in _load_trick_definitions_cached(csv_path_str):
        for _ in range(card_def.copies):
            deck.append(TrickCard(deck_index=deck_index, name=card_def.name, description=card_def.description))
            deck_index += 1
    return tuple(deck)


def build_trick_deck(csv_path: str | Path | None = None) -> list[TrickCard]:
    return list(_build_trick_deck_cached(str(_resolve_csv_path(csv_path))))
