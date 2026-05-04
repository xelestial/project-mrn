from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Dict, Tuple


@dataclass(frozen=True, slots=True)
class CharacterDef:
    name: str
    pair: str
    card_no: int
    ability_text: str
    priority: int
    attribute: str
    starting_active: bool


CHARACTERS: Dict[str, CharacterDef] = {
    "어사": CharacterDef("어사", "탐관오리", 1, "[속성] - [무뢰]속성 인물은 인물 능력 사용불가", 1, "관원", True),
    "탐관오리": CharacterDef("탐관오리", "어사", 1, "[속성] - [관원, 상민]속성 인물은 탐관오리에게 미리내 조각 2개 마다 1냥 지급하고 이동 시 주사위 1개를 추가하여 굴림", 1, "무뢰", False),
    "자객": CharacterDef("자객", "산적", 2, "[지목] - 지목 인물은 인물카드를 공개하고 차례 넘기며 어떤 지목효과도 받지 않음.", 2, "무뢰", True),
    "산적": CharacterDef("산적", "자객", 2, "[지목] - 지목 인물은 산적의 미리내 조각 1개 마다 1냥 지급", 2, "무뢰", False),
    "추노꾼": CharacterDef("추노꾼", "탈출 노비", 3, "[지목] - 대상 인물은 추노꾼 위치로 도착하여 턴 시작, 대상은 출발 칸 경유하여도 조각 받지 못함", 3, "잡인", True),
    "탈출 노비": CharacterDef("탈출 노비", "추노꾼", 3, "[도착] - 시작, 종료, 운수 칸 보다 1칸 부족한 경우 해당 칸으로 도착 할 수 있음", 3, "잡인", False),
    "파발꾼": CharacterDef("파발꾼", "아전", 4, "[능력1] 이번 턴 주사위를 1개 추가해 굴림(중복 눈이면 1회 추가 굴림) / [능력2] 조각 8+이면 주사위를 1개 줄여 굴림(능력1/2 중 택1)", 4, "관원", True),
    "아전": CharacterDef("아전", "파발꾼", 4, "[도착] - 다른 참가자의 말이 있는 토지에 도착하면 통행료 면제, 같은 칸에 있는 참가자들은 아전의 미리내 조각 1개 마다 1냥 지급", 4, "관원", False),
    "교리 연구관": CharacterDef("교리 연구관", "교리 감독관", 5, "[능력1] 라운드 종료 시 붉은 징표 획득(드래프트 전달: 반시계) / [능력2] 조각 8+이면 짐 1장 제거", 5, "종교인", True),
    "교리 감독관": CharacterDef("교리 감독관", "교리 연구관", 5, "[능력1] 라운드 종료 시 보라 징표 획득(드래프트 전달: 시계) / [능력2] 조각 8+이면 짐 1장 제거", 5, "종교인", False),
    "박수": CharacterDef("박수", "만신", 6, "[능력1] 지목 성공 시 짐 이관+잔꾀 수급 / [능력2] 지목 실패 시 조각 6+면 짐 1장 제거 후 제거비용 획득", 6, "잡인", True),
    "만신": CharacterDef("만신", "박수", 6, "[능력1] 지목 성공 시 대상 짐 전량 제거+비용 수급 / [능력2] 지목 실패 시 조각 8+면 짐 1장 제거 후 제거비용 획득", 6, "잡인", False),
    "객주": CharacterDef("객주", "중매꾼", 7, "[능력] 랩 보상 선택 항목별 +1, 종료칸 조각 2배, 자가 토지 도착 시 승점 +1", 7, "상민", True),
    "중매꾼": CharacterDef("중매꾼", "객주", 7, "[능력1] 인접 토지 추가 매입(기본 2배) / [능력2] 조각 8+이면 인접 토지 추가 매입 1배", 7, "상민", False),
    "건설업자": CharacterDef("건설업자", "사기꾼", 8, "[능력] 이번 턴 토지 무료 구입", 8, "상민", True),
    "사기꾼": CharacterDef("사기꾼", "건설업자", 8, "[능력1] 통행료 3배로 토지 인수 / [능력2] 조각 8+면 통행료 2배로 토지 인수", 8, "상민", False),
}

CARD_TO_NAMES: Dict[int, Tuple[str, str]] = {
    1: ("어사", "탐관오리"),
    2: ("자객", "산적"),
    3: ("추노꾼", "탈출 노비"),
    4: ("파발꾼", "아전"),
    5: ("교리 연구관", "교리 감독관"),
    6: ("박수", "만신"),
    7: ("객주", "중매꾼"),
    8: ("건설업자", "사기꾼"),
}

STARTING_ACTIVE_BY_CARD: Dict[int, str] = {}
for name, c in CHARACTERS.items():
    if c.starting_active:
        STARTING_ACTIVE_BY_CARD[c.card_no] = name



def randomized_active_by_card(rng: random.Random | None = None) -> Dict[int, str]:
    """Return a per-card random active-face map.

    The RNG is injected so seeded simulations remain reproducible.
    """
    chooser = (rng.choice if rng is not None else random.choice)
    return {card_no: chooser(names) for card_no, names in CARD_TO_NAMES.items()}
