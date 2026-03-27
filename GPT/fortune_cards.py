from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True, slots=True)
class FortuneCardDef:
    copies: int
    name: str
    effect: str


@dataclass(frozen=True, slots=True)
class FortuneCard:
    deck_index: int
    name: str
    effect: str


def _default_csv_path() -> Path:
    return Path(__file__).with_name("fortune.csv")


def _resolve_csv_path(csv_path: str | Path | None = None) -> Path:
    path = Path(csv_path) if csv_path is not None else _default_csv_path()
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).with_name(str(path))
    return path.resolve()


@lru_cache(maxsize=None)
def _load_fortune_definitions_cached(csv_path_str: str) -> Tuple[FortuneCardDef, ...]:
    path = Path(csv_path_str)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        defs: list[FortuneCardDef] = []
        for row in reader:
            raw_copies = (row.get("카드 장수") or "").strip()
            raw_name = " ".join((row.get("이름") or "").split())
            raw_effect = (row.get("효과") or "").strip()
            if not raw_copies or not raw_name or not raw_effect:
                continue
            defs.append(FortuneCardDef(copies=int(raw_copies), name=raw_name, effect=raw_effect))
        return tuple(defs)


def load_fortune_definitions(csv_path: str | Path | None = None) -> list[FortuneCardDef]:
    return list(_load_fortune_definitions_cached(str(_resolve_csv_path(csv_path))))


@lru_cache(maxsize=None)
def _build_fortune_deck_cached(csv_path_str: str) -> Tuple[FortuneCard, ...]:
    deck: list[FortuneCard] = []
    deck_index = 1
    for card_def in _load_fortune_definitions_cached(csv_path_str):
        for _ in range(card_def.copies):
            deck.append(FortuneCard(deck_index=deck_index, name=card_def.name, effect=card_def.effect))
            deck_index += 1
    return tuple(deck)


def build_fortune_deck(csv_path: str | Path | None = None) -> list[FortuneCard]:
    return list(_build_fortune_deck_cached(str(_resolve_csv_path(csv_path))))
