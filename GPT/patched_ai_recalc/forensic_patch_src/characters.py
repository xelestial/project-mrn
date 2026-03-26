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
    "자객": CharacterDef("자객", "산적", 2, "[지목] - 지목 인물은 인물카드를 공개하고 차례 넘기며 어떤 지목효과도 받지 않음.", 2, "무뢰", False),
    "산적": CharacterDef("산적", "자객", 2, "[지목] - 지목 인물은 산적의 미리내 조각 1개 마다 1냥 지급", 2, "무뢰", True),
    "추노꾼": CharacterDef("추노꾼", "탈출 노비", 3, "[지목] - 대상 인물은 추노꾼 위치로 도착하여 턴 시작, 대상은 출발 칸 경유하여도 조각 받지 못함", 3, "잡인", True),
    "탈출 노비": CharacterDef("탈출 노비", "추노꾼", 3, "[도착] - 시작, 종료, 운수 칸 보다 1칸 부족한 경우 해당 칸으로 도착 할 수 있음", 3, "잡인", False),
    "파발꾼": CharacterDef("파발꾼", "아전", 4, "[효과] - 이번 턴 주사위 1개 더 이용하여 굴림 / [효과] - 이동 시 주사위의 같은 눈 수가 2개 나오면 이동 처리하고 1회에 한하여 한 번 더 굴림", 4, "관원", True),
    "아전": CharacterDef("아전", "파발꾼", 4, "[도착] - 다른 참가자의 말이 있는 토지에 도착하면 통행료 면제, 같은 칸에 있는 참가자들은 아전의 미리내 조각 1개 마다 1냥 지급", 4, "관원", False),
    "교리 연구관": CharacterDef("교리 연구관", "교리 감독관", 5, "[액티브] 자신 또는 팀원의 짐 카드 1장을 제거합니다. [징표관리] - 턴 종료 후 징표를 가져옵니다. 연구관의 징표는 시계방향으로 흐릅니다.", 5, "종교인", True),
    "교리 감독관": CharacterDef("교리 감독관", "교리 연구관", 5, "[액티브] 자신 또는 팀원의 짐 카드 1장을 제거합니다. [징표관리] - 턴 종료 후 징표를 가져옵니다. 감독관의 징표는 반시계 방향으로 흐릅니다", 5, "종교인", False),
    "박수": CharacterDef("박수", "만신", 6, "[지목] 소유한 가벼운 짐 또는 무거운 짐을 대상에게 넘겨주고 넘겨준 장수만큼 잔꾀를 받아옵니다", 6, "잡인", True),
    "만신": CharacterDef("만신", "박수", 6, "[지목] 대상이 보유한 가벼운 짐 또는 무거운 짐을 모두 제거하고 제거 비용만큼 만신에게 지급", 6, "잡인", False),
    "객주": CharacterDef("객주", "중매꾼", 7, "[효과] 종료(시작)칸 경유 마다 돈,조각,승점(택 1)을 1개 더 받음 / [도착] 자신의 토지에 도착할 때 승점을 1개 받습니다", 7, "상민", False),
    "중매꾼": CharacterDef("중매꾼", "객주", 7, "[도착] - 같은 색깔 구역의 인접 토지를 같이 매입할 수 있음, 도착 칸이 소유자가 있어도 인접 지역 매입 가능", 7, "상민", True),
    "건설업자": CharacterDef("건설업자", "사기꾼", 8, "[효과] - 이번 턴 토지 무료 구입", 8, "잡인", True),
    "사기꾼": CharacterDef("사기꾼", "건설업자", 8, "[도착] - 통행료의 2배 지급하고 방문 토지 인수함, 인수할 때 해당 토지에 적립된 승점도 같이 인수합니다", 8, "무뢰", False),
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
