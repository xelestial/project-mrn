from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from game_rules import DiceRules, EconomyRules, EndConditionRules, ForceSaleRules, GameRules, LapRewardRules, ResourceRules, SpecialTileRules, StartRewardRules, TakeoverRules, TokenRules


_MODULE_DIR = Path(__file__).resolve().parent


def _resolve_ruleset_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    fallback = _MODULE_DIR / candidate
    if fallback.exists():
        return fallback
    return candidate


def _pick(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return default


def rules_from_dict(raw: dict[str, Any] | None) -> GameRules:
    raw = dict(raw or {})
    token_raw = dict(raw.get('token') or {})
    lap_raw = dict(raw.get('lap_reward') or raw.get('lap') or {})
    start_reward_raw = dict(raw.get('start_reward') or raw.get('start') or raw.get('initial_reward') or {})
    takeover_raw = dict(raw.get('takeover') or {})
    force_sale_raw = dict(raw.get('force_sale') or {})
    end_raw = dict(raw.get('end') or {})
    economy_raw = dict(raw.get('economy') or {})
    resources_raw = dict(raw.get('resources') or raw.get('resource') or {})
    dice_raw = dict(raw.get('dice') or raw.get('dice_cards') or {})
    special_raw = dict(raw.get('special_tiles') or raw.get('special') or {})
    return GameRules(
        token=TokenRules(
            starting_hand_coins=int(_pick(token_raw, 'starting_hand_coins', default=0)),
            lap_reward_coins=int(_pick(token_raw, 'lap_reward_coins', default=_pick(lap_raw, 'coins', default=3))),
            max_coins_per_tile=int(_pick(token_raw, 'max_coins_per_tile', default=3)),
            max_place_per_visit=int(_pick(token_raw, 'max_place_per_visit', default=3)),
            can_place_on_first_purchase=bool(_pick(token_raw, 'can_place_on_first_purchase', default=True)),
            max_place_on_purchase=int(_pick(token_raw, 'max_place_on_purchase', default=1)),
            transfer_coins_on_takeover=bool(_pick(token_raw, 'transfer_coins_on_takeover', default=True)),
        ),
        lap_reward=LapRewardRules(
            cash=int(_pick(lap_raw, 'cash', default=5)),
            coins=int(_pick(lap_raw, 'coins', default=_pick(token_raw, 'lap_reward_coins', default=3))),
            shards=int(_pick(lap_raw, 'shards', default=3)),
            points_budget=int(_pick(lap_raw, 'points_budget', 'budget', default=10)),
            cash_point_cost=int(_pick(lap_raw, 'cash_point_cost', default=2)),
            shards_point_cost=int(_pick(lap_raw, 'shards_point_cost', default=3)),
            coins_point_cost=int(_pick(lap_raw, 'coins_point_cost', default=3)),
            cash_pool=int(_pick(lap_raw, 'cash_pool', default=30)),
            shards_pool=int(_pick(lap_raw, 'shards_pool', default=18)),
            coins_pool=int(_pick(lap_raw, 'coins_pool', default=18)),
        ),
        start_reward=StartRewardRules(
            points_budget=int(_pick(start_reward_raw, 'points_budget', 'budget', default=20)),
            cash_point_cost=int(_pick(start_reward_raw, 'cash_point_cost', default=2)),
            shards_point_cost=int(_pick(start_reward_raw, 'shards_point_cost', default=3)),
            coins_point_cost=int(_pick(start_reward_raw, 'coins_point_cost', default=3)),
            cash_pool=int(_pick(start_reward_raw, 'cash_pool', default=30)),
            shards_pool=int(_pick(start_reward_raw, 'shards_pool', default=18)),
            coins_pool=int(_pick(start_reward_raw, 'coins_pool', default=18)),
        ),
        takeover=TakeoverRules(
            blocked_by_monopoly=bool(_pick(takeover_raw, 'blocked_by_monopoly', default=True)),
            transfer_tile_coins=bool(_pick(takeover_raw, 'transfer_tile_coins', default=True)),
        ),
        force_sale=ForceSaleRules(
            refund_purchase_cost=bool(_pick(force_sale_raw, 'refund_purchase_cost', default=True)),
            return_tile_coins_to_original_owner=bool(_pick(force_sale_raw, 'return_tile_coins_to_original_owner', default=True)),
            block_repurchase_until_next_turn=bool(_pick(force_sale_raw, 'block_repurchase_until_next_turn', default=True)),
        ),
        end=EndConditionRules(
            f_threshold=None if _pick(end_raw, 'f_threshold', default=15.0) is None else float(_pick(end_raw, 'f_threshold', default=15.0)),
            monopolies_to_trigger_end=int(_pick(end_raw, 'monopolies_to_trigger_end', default=3)),
            tiles_to_trigger_end=None if _pick(end_raw, 'tiles_to_trigger_end', default=9) is None else int(_pick(end_raw, 'tiles_to_trigger_end', default=9)),
            alive_players_at_most=int(_pick(end_raw, 'alive_players_at_most', default=2)),
        ),
        economy=EconomyRules(
            starting_cash=int(_pick(economy_raw, 'starting_cash', default=20)),
            land_profiles={
                str(name): (int(vals[0]), int(vals[1]))
                for name, vals in dict(_pick(economy_raw, 'land_profiles', default={'HIGH': [5, 5], 'MID': [4, 4], 'LOW': [3, 3]})).items()
            },
        ),
        resources=ResourceRules(
            starting_shards=int(_pick(resources_raw, 'starting_shards', default=2)),
        ),
        dice=DiceRules(
            enabled=bool(_pick(dice_raw, 'enabled', default=True)),
            values=tuple(int(v) for v in _pick(dice_raw, 'values', default=(1, 2, 3, 4, 5, 6))),
            one_shot=bool(_pick(dice_raw, 'one_shot', default=True)),
            max_cards_per_turn=int(_pick(dice_raw, 'max_cards_per_turn', default=2)),
            use_one_card_plus_one_die=bool(_pick(dice_raw, 'use_one_card_plus_one_die', default=True)),
        ),
        special_tiles=SpecialTileRules(
            s_display_name=str(_pick(special_raw, 's_display_name', default='운수')),
            f1_increment=float(_pick(special_raw, 'f1_increment', default=1.0)),
            f2_increment=float(_pick(special_raw, 'f2_increment', default=2.0)),
            f1_shards=int(_pick(special_raw, 'f1_shards', default=1)),
            f2_shards=int(_pick(special_raw, 'f2_shards', default=2)),
            malicious_land_multiplier=int(_pick(special_raw, 'malicious_land_multiplier', default=3)),
            s_cash_plus1_probability=float(_pick(special_raw, 's_cash_plus1_probability', default=0.50)),
            s_cash_plus2_probability=float(_pick(special_raw, 's_cash_plus2_probability', default=0.25)),
            s_cash_minus1_probability=float(_pick(special_raw, 's_cash_minus1_probability', default=0.25)),
        ),
    )


def load_ruleset(path: str | None) -> GameRules | None:
    if not path:
        return None
    p = _resolve_ruleset_path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding='utf-8'))
    return rules_from_dict(data.get('rules', data))


def rules_to_dict(rules: GameRules) -> dict[str, Any]:
    return {
        'rules': {
            'token': asdict(rules.token),
            'lap_reward': asdict(rules.lap_reward),
            'start_reward': asdict(rules.start_reward),
            'takeover': asdict(rules.takeover),
            'force_sale': asdict(rules.force_sale),
            'end': asdict(rules.end),
            'economy': asdict(rules.economy),
            'resources': asdict(rules.resources),
            'dice': asdict(rules.dice),
            'special_tiles': asdict(rules.special_tiles),
        }
    }


def save_ruleset(path: str | Path, rules: GameRules) -> None:
    p = _resolve_ruleset_path(path)
    p.write_text(json.dumps(rules_to_dict(rules), ensure_ascii=False, indent=2), encoding='utf-8')
