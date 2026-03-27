from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True, slots=True)
class WeatherCardDef:
    copies: int
    name: str
    effect: str


@dataclass(frozen=True, slots=True)
class WeatherCard:
    deck_index: int
    name: str
    effect: str


WEATHER_ZONE_COLORS: tuple[str, ...] = (
    "검은색", "빨간색", "노란색", "파란색", "하얀색", "초록색",
    "검은색", "빨간색", "노란색", "파란색", "하얀색", "초록색",
)


COLOR_RENT_DOUBLE_WEATHERS = {
    "검은 달": "검은색",
    "휴가철": "빨간색",
    "어린이 보호구역": "노란색",
    "바다다!": "파란색",
    "멋진 설경": "하얀색",
    "곡식가득한 평야": "초록색",
}


def _default_csv_path() -> Path:
    return Path(__file__).with_name("weather.csv")


def _resolve_csv_path(csv_path: str | Path | None = None) -> Path:
    path = Path(csv_path) if csv_path is not None else _default_csv_path()
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).with_name(str(path))
    return path.resolve()


@lru_cache(maxsize=None)
def _load_weather_definitions_cached(csv_path_str: str) -> Tuple[WeatherCardDef, ...]:
    path = Path(csv_path_str)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        defs: list[WeatherCardDef] = []
        for row in reader:
            raw_copies = (row.get("매수") or "").strip()
            raw_name = " ".join((row.get("이름") or "").split())
            raw_effect = (row.get("효과") or "").strip()
            if not raw_copies or not raw_name or not raw_effect:
                continue
            defs.append(WeatherCardDef(copies=int(raw_copies), name=raw_name, effect=raw_effect))
        return tuple(defs)


def load_weather_definitions(csv_path: str | Path | None = None) -> list[WeatherCardDef]:
    return list(_load_weather_definitions_cached(str(_resolve_csv_path(csv_path))))


@lru_cache(maxsize=None)
def _build_weather_deck_cached(csv_path_str: str) -> Tuple[WeatherCard, ...]:
    deck: list[WeatherCard] = []
    deck_index = 1
    for card_def in _load_weather_definitions_cached(csv_path_str):
        for _ in range(card_def.copies):
            deck.append(WeatherCard(deck_index=deck_index, name=card_def.name, effect=card_def.effect))
            deck_index += 1
    return tuple(deck)


def build_weather_deck(csv_path: str | Path | None = None) -> list[WeatherCard]:
    return list(_build_weather_deck_cached(str(_resolve_csv_path(csv_path))))
