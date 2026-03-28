from __future__ import annotations

from characters import CARD_TO_NAMES, CHARACTERS


def character_card_no(name: str | None) -> int | None:
    if not name:
        return None
    meta = CHARACTERS.get(name)
    return None if meta is None else meta.card_no


def is_card_face(name: str | None, card_no: int, face_index: int) -> bool:
    if not name:
        return False
    try:
        return name == CARD_TO_NAMES[card_no][face_index]
    except KeyError:
        return False


def is_baksu(name: str | None) -> bool:
    return is_card_face(name, 6, 0)


def is_eosa(name: str | None) -> bool:
    return is_card_face(name, 1, 0)


def is_gakju(name: str | None) -> bool:
    return is_card_face(name, 7, 0)


def is_mansin(name: str | None) -> bool:
    return is_card_face(name, 6, 1)


def is_assassin(name: str | None) -> bool:
    return is_card_face(name, 2, 0)


def is_bandit(name: str | None) -> bool:
    return is_card_face(name, 2, 1)


def is_tamgwanori(name: str | None) -> bool:
    return is_card_face(name, 1, 1)


def is_pabalggun(name: str | None) -> bool:
    return is_card_face(name, 4, 0)


def is_ajeon(name: str | None) -> bool:
    return is_card_face(name, 4, 1)


def is_chunokkun(name: str | None) -> bool:
    return is_card_face(name, 3, 0)


def is_token_window_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0], CARD_TO_NAMES[8][1]}


def is_builder_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0]}


def is_swindler(name: str | None) -> bool:
    return is_card_face(name, 8, 1)


def is_growth_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0], CARD_TO_NAMES[8][1]}


def is_controller_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def is_direct_denial_character(name: str | None) -> bool:
    return (
        is_assassin(name)
        or is_bandit(name)
        or is_chunokkun(name)
        or is_pabalggun(name)
        or is_baksu(name)
        or is_mansin(name)
        or is_eosa(name)
    )


def is_route_runner_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[4][0], CARD_TO_NAMES[7][0], CARD_TO_NAMES[3][1]}


def is_primary_lap_runner_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[4][0], CARD_TO_NAMES[7][0]}


def is_shard_hunter_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[2][1], CARD_TO_NAMES[1][1], CARD_TO_NAMES[4][1]}


def escape_package_names() -> set[str]:
    return {CARD_TO_NAMES[6][0], CARD_TO_NAMES[6][1], CARD_TO_NAMES[3][1]}


def marker_package_names() -> set[str]:
    return {CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def is_cleanup_character(name: str | None) -> bool:
    if not name:
        return False
    return name in {CARD_TO_NAMES[6][0], CARD_TO_NAMES[6][1], CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def active_money_drain_names() -> set[str]:
    return {CARD_TO_NAMES[1][1], CARD_TO_NAMES[2][1], CARD_TO_NAMES[4][1], CARD_TO_NAMES[3][0], CARD_TO_NAMES[6][1]}


def is_active_money_drain_character(name: str | None) -> bool:
    return bool(name and name in active_money_drain_names())


def low_cash_income_names() -> set[str]:
    return {CARD_TO_NAMES[7][0], CARD_TO_NAMES[4][1], CARD_TO_NAMES[6][1]}


def low_cash_escape_names() -> set[str]:
    return {CARD_TO_NAMES[7][0], CARD_TO_NAMES[4][0], CARD_TO_NAMES[3][1]}


def low_cash_controller_names() -> set[str]:
    return {CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def low_cash_disruptor_names() -> set[str]:
    return {CARD_TO_NAMES[2][0], CARD_TO_NAMES[4][1], CARD_TO_NAMES[6][1], CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def is_low_cash_escape_character(name: str | None) -> bool:
    return bool(name and name in low_cash_escape_names())


def is_low_cash_income_character(name: str | None) -> bool:
    return bool(name and name in low_cash_income_names())


def is_low_cash_controller_character(name: str | None) -> bool:
    return bool(name and name in low_cash_controller_names())


def is_low_cash_disruptor_character(name: str | None) -> bool:
    return bool(name and name in low_cash_disruptor_names())
