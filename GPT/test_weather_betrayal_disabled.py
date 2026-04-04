import random

from config import DEFAULT_CONFIG
from engine import GameEngine
from policy.factory import PolicyFactory
from state import GameState
from weather_cards import WeatherCard


def _make_engine(seed: int = 7) -> GameEngine:
    rng = random.Random(seed)
    policy = PolicyFactory.create_runtime_policy(
        policy_mode="arena",
        lap_policy_mode="heuristic_v3_gpt",
        rng=rng,
    )
    return GameEngine(DEFAULT_CONFIG, policy, rng=rng, enable_logging=True)


def test_betrayal_weather_is_explicit_no_op() -> None:
    engine = _make_engine()
    state = GameState.create(DEFAULT_CONFIG)
    state.marker_owner_id = 2
    state.marker_draft_clockwise = False
    state.weather_draw_pile = [
        WeatherCard(
            deck_index=9999,
            name="배신의 징표",
            effect="[현재 효과 없음]",
        )
    ]

    engine._apply_round_weather(state)

    assert state.marker_owner_id == 2
    assert state.marker_draft_clockwise is False
    weather_row = next((row for row in reversed(engine._action_log) if row.get("event") == "weather_round"), None)
    assert weather_row is not None
    assert weather_row.get("weather") == "배신의 징표"
    details = weather_row.get("details") or []
    assert details
    assert details[0].get("effect") == "disabled_no_op"
