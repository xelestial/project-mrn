import json
import random
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_policy import BasePolicy, HeuristicPolicy, MovementDecision, LapRewardDecision
from apps.server.src.services.decision_gateway import (
    _build_burden_exchange_context,
    _build_coin_placement_choices,
    _build_geo_bonus_choices,
    _build_lap_reward_legal_choices,
    _build_movement_legal_choices,
    _build_runaway_legal_choices,
)
from config import DEFAULT_CONFIG, CellKind
from engine import GameEngine
from state import GameState
from characters import CARD_TO_NAMES
from policy_mark_utils import ordered_public_mark_targets
from trick_cards import TrickCard, build_trick_deck
from fortune_cards import FortuneCard
from viewer.stream import VisEventStream


class DummyPolicy(BasePolicy):
    def choose_movement(self, state, player):
        return MovementDecision(False, ())

    def choose_lap_reward(self, state, player):
        return LapRewardDecision("cash")

    def choose_coin_placement_tile(self, state, player):
        return None

    def choose_draft_card(self, state, player, offered_cards):
        return offered_cards[0]

    def choose_final_character(self, state, player, card_choices):
        raise NotImplementedError

    def choose_mark_target(self, state, player, actor_name):
        return None

    def choose_geo_bonus(self, state, player, actor_name):
        return "cash"

    def choose_trick_tile_target(self, state, player, card_name, candidate_tiles, target_scope="any"):
        return candidate_tiles[0] if candidate_tiles else None


class TargetPolicy(DummyPolicy):
    def __init__(self, target_name=None):
        self.target_name = target_name

    def choose_mark_target(self, state, player, actor_name):
        return self.target_name


class PabalModePolicy(DummyPolicy):
    def __init__(self, mode: str):
        self._mode = mode

    def choose_pabal_dice_mode(self, state, player):
        return self._mode


class FixedRandom(random.Random):
    def __new__(cls, values):
        # random.Random.__new__ tries to seed from the first argument on some Python
        # versions, so ensure list inputs never flow into that path.
        return random.Random.__new__(cls)

    def __init__(self, values):
        super().__init__(0)
        self.values = list(values)

    def randint(self, a, b):
        if not self.values:
            raise AssertionError("No more predetermined dice values")
        return self.values.pop(0)




def block_land_positions(state, block_id):
    return state.block_tile_positions(block_id, land_only=True)


def first_land_positions(state, block_id=1):
    return block_land_positions(state, block_id)


def first_three_land_block_positions(state):
    for block_id in sorted(set(state.block_ids)):
        if block_id > 0:
            positions = state.block_tile_positions(block_id, land_only=True)
            if len(positions) >= 3:
                return positions
    raise AssertionError("No 3-land block found")


def first_special_position(state, kind):
    return state.first_tile_position(kinds=[kind])


def first_t3_position(state):
    return state.first_tile_position(kinds=[CellKind.T3])


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_selector_scene_fixture() -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.scene.turn_resolution.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_selector_player_fixture() -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.player.mark_target_visibility.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_selector_prompt_fixture(name: str) -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


class RuleFixTests(unittest.TestCase):
    def make_engine(self, policy=None, rng=None):
        return GameEngine(DEFAULT_CONFIG, policy or DummyPolicy(), rng=rng or random.Random(0), enable_logging=True)

    def make_state(self, engine):
        state = GameState.create(DEFAULT_CONFIG)
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        return state

    def test_eosa_blocks_only_other_muroe_skills_and_not_same_card_tamgwan(self):
        engine = self.make_engine(rng=FixedRandom([2, 3]))
        state = self.make_state(engine)
        eosa = state.players[0]
        target = state.players[1]

        eosa.current_character = "어사"
        target.current_character = "아전"
        target.cash = 20

        move, meta = engine._resolve_move(state, target, MovementDecision(False, ()))
        self.assertEqual(move, 5)
        self.assertEqual(meta["dice"], [2, 3])
        self.assertEqual(target.cash, 20)

        swindler = state.players[3]
        swindler.current_character = "사기꾼"
        protected_pos = first_land_positions(state)[0]
        swindler.position = protected_pos
        swindler.cash = 20
        state.tile_owner[protected_pos] = target.player_id
        state.tile_coins[protected_pos] = 2
        target.tiles_owned = 1
        target.score_coins_placed = 2
        result = engine._resolve_landing(state, swindler)
        self.assertEqual(result["type"], "SWINDLE_TAKEOVER")
        self.assertEqual(state.tile_owner[protected_pos], swindler.player_id)
        self.assertEqual(swindler.score_coins_placed, 2)
        self.assertEqual(target.score_coins_placed, 0)
        self.assertEqual(result.get("swindle_multiplier"), 3)

    def test_tamgwan_uses_own_shards_for_tribute_and_extra_die(self):
        engine = self.make_engine(rng=FixedRandom([2, 3, 4]))
        state = self.make_state(engine)
        tam = state.players[0]
        target = state.players[1]

        tam.current_character = "탐관오리"
        tam.shards = 5
        target.current_character = "아전"
        target.shards = 0
        target.cash = 20

        move, meta = engine._resolve_move(state, target, MovementDecision(False, ()))
        self.assertEqual(move, 9)
        self.assertEqual(meta["dice"], [2, 3, 4])
        self.assertEqual(target.cash, 18)
        self.assertEqual(tam.cash, DEFAULT_CONFIG.economy.starting_cash + 2)

    def test_swindler_takes_tile_and_score_coins_together(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        swindler = state.players[0]
        owner = state.players[1]
        swindler.current_character = "사기꾼"
        swindler.cash = 20
        swindler.position = first_t3_position(state)
        owner.current_character = "아전"
        owner.tiles_owned = 1
        owner.score_coins_placed = 3
        state.tile_owner[swindler.position] = owner.player_id
        state.tile_coins[swindler.position] = 3
        result = engine._resolve_landing(state, swindler)
        self.assertEqual(result["type"], "SWINDLE_TAKEOVER")
        self.assertEqual(result["coins_taken"], 3)
        self.assertEqual(state.tile_owner[swindler.position], swindler.player_id)
        self.assertEqual(state.tile_coins[swindler.position], 3)
        self.assertEqual(swindler.tiles_owned, 1)
        self.assertEqual(owner.tiles_owned, 0)
        self.assertEqual(swindler.score_coins_placed, 3)
        self.assertEqual(owner.score_coins_placed, 0)

    def test_purchase_places_at_most_one_score_coin_on_purchased_tile(self):
        class PurchasePlacePolicy(DummyPolicy):
            def choose_purchase_tile(self, state, player, pos, cell, cost, source=None):
                return True

            def choose_coin_placement_tile(self, state, player):
                return None

        engine = self.make_engine(policy=PurchasePlacePolicy())
        state = self.make_state(engine)
        player = state.players[0]
        player.current_character = "객주"
        player.cash = 20
        player.hand_coins = 3
        pos = first_land_positions(state)[0]
        player.position = pos
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertIsNotNone(result.get("placed"))
        self.assertEqual(result["placed"]["target"], pos)
        self.assertEqual(result["placed"]["amount"], 1)
        self.assertEqual(state.tile_coins[pos], 1)
        self.assertEqual(player.hand_coins, 2)

    def test_force_sale_returns_score_coins_to_original_owner_hand(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        seller = state.players[0]
        attacker = state.players[1]
        seller.current_character = "객주"
        attacker.current_character = "아전"
        pos = first_land_positions(state)[0]
        state.tile_owner[pos] = seller.player_id
        state.tile_coins[pos] = 2
        state.players[seller.player_id].tiles_owned = 1
        state.players[seller.player_id].score_coins_placed = 2
        seller.hand_coins = 0
        seller.trick_hand = []
        attacker.trick_hand = [type("Tmp", (), {"name": "강제 매각", "deck_index": 999})()]
        result = engine._apply_force_sale(state, attacker, pos)
        self.assertEqual(result["type"], "FORCE_SALE")
        self.assertEqual(result["returned_coins"], 2)
        self.assertEqual(seller.hand_coins, 2)
        self.assertEqual(seller.score_coins_placed, 0)
        self.assertEqual(state.tile_coins[pos], 0)

    def test_baksu_transfers_burdens_and_draws_tricks(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        baksu = state.players[0]
        target = state.players[1]
        baksu.current_character = "박수"
        target.current_character = "아전"
        baksu.trick_hand = [c for c in state.trick_draw_pile if c.name == "가벼운 짐"][:1]
        state.trick_draw_pile = [c for c in state.trick_draw_pile if c.deck_index != baksu.trick_hand[0].deck_index]
        target.pending_marks.append({"type": "baksu_transfer", "source_pid": baksu.player_id})
        engine._resolve_pending_marks(state, target)
        self.assertEqual(sum(1 for c in target.trick_hand if c.name == "가벼운 짐"), 1)
        self.assertEqual(len(baksu.trick_hand), 1)
        self.assertNotEqual(baksu.trick_hand[0].name, "가벼운 짐")

    def test_hunter_pull_forces_landing_without_lap_credit(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        target = state.players[1]
        owner = state.players[2]
        target.current_character = "아전"
        owner.current_character = "객주"
        target.position = len(state.board) // 4
        target.total_steps = 54
        target.cash = 20
        rent_pos = first_land_positions(state)[0]
        state.tile_owner[rent_pos] = owner.player_id
        owner.tiles_owned = 1
        target.pending_marks.append({"type": "hunter_pull", "source_pid": 0, "source_pos": rent_pos})
        engine._resolve_pending_marks(state, target)
        self.assertEqual(target.position, rent_pos)
        self.assertEqual(target.total_steps, 54)
        self.assertEqual(target.cash, 15)

    def test_matchmaker_purchase_fail_skips_without_bankruptcy(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 2
        player.position = 2
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE_FAIL")
        self.assertTrue(player.alive)
        self.assertFalse(result.get("bankrupt", True))
        self.assertTrue(result.get("skipped", False))
        self.assertNotIn("adjacent_bought", result)
        self.assertIsNone(state.tile_owner[first_land_positions(state)[0]])

    def test_matchmaker_buys_only_one_adjacent_tile(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 20
        player.position = first_three_land_block_positions(state)[1]  # middle land in a 3-land block
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(len(result.get("adjacent_bought", [])), 1)
        owned = {i for i, owner in enumerate(state.tile_owner) if owner == player.player_id}
        block_lands = first_three_land_block_positions(state)
        self.assertIn(owned, ({block_lands[0], block_lands[1]}, {block_lands[1], block_lands[2]}))

    def test_matchmaker_can_trigger_on_rent_landing(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        owner = state.players[1]
        player.current_character = "중매꾼"
        player.cash = 20
        owner.tiles_owned = 1
        block_lands = first_three_land_block_positions(state)
        state.tile_owner[block_lands[1]] = owner.player_id
        player.position = block_lands[1]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "RENT")
        self.assertEqual(len(result.get("adjacent_bought", [])), 1)

    def test_matchmaker_can_buy_landing_tile_without_shard(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 20
        player.shards = 0
        player.position = first_land_positions(state)[0]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("shard_cost"), 0)
        self.assertEqual(player.shards, 0)
        self.assertEqual(state.tile_owner[first_land_positions(state)[0]], player.player_id)

    def test_matchmaker_does_not_spend_shard_on_adjacent_buy(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 20
        player.shards = 1
        player.position = first_three_land_block_positions(state)[1]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("shard_cost"), 0)
        self.assertEqual(player.shards, 1)
        self.assertEqual(len(result.get("adjacent_bought", [])), 1)


    def test_matchmaker_adjacent_buy_without_shard_still_allowed(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 20
        player.shards = 0
        player.position = first_three_land_block_positions(state)[1]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("shard_cost"), 0)
        self.assertEqual(player.shards, 0)
        self.assertEqual(len(result.get("adjacent_bought", [])), 1)

    def test_matchmaker_middle_land_allows_selecting_between_adjacent_tiles(self):
        class AdjacentChoicePolicy(DummyPolicy):
            def choose_trick_tile_target(self, state, player, card_name, candidate_tiles, target_scope="any"):
                self.recorded_candidates = list(candidate_tiles)
                return candidate_tiles[-1]

            def choose_purchase_tile(self, state, player, pos, cell, cost, source=None):
                return True

        policy = AdjacentChoicePolicy()
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 20
        player.shards = 0
        middle = first_three_land_block_positions(state)[1]
        left, _, right = first_three_land_block_positions(state)
        player.position = middle

        result = engine._resolve_landing(state, player)

        self.assertEqual(policy.recorded_candidates, [left, right])
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("adjacent_bought"), [right])

    def test_builder_gets_free_landing_purchase_without_spending_shards(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "건설업자"
        player.cash = 20
        player.shards = 0
        player.position = first_three_land_block_positions(state)[1]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("cost"), 0)
        self.assertEqual(result.get("shard_cost"), 0)
        self.assertEqual(player.cash, 20)
        self.assertEqual(player.shards, 0)

    def test_builder_keeps_existing_shards_on_free_landing_purchase(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "건설업자"
        player.cash = 20
        player.shards = 3
        player.position = first_three_land_block_positions(state)[1]
        result = engine._resolve_landing(state, player)
        self.assertEqual(result["type"], "PURCHASE")
        self.assertEqual(result.get("cost"), 0)
        self.assertEqual(result.get("shard_cost"), 0)
        self.assertEqual(player.cash, 20)
        self.assertEqual(player.shards, 3)

    def test_runaway_slave_gets_plus_one_to_special_tile(self):
        engine = self.make_engine(rng=FixedRandom([1, 1]))
        state = self.make_state(engine)
        player = state.players[0]
        player.current_character = "탈출 노비"
        player.position = 0  # move 2 -> index 2, one short of S at 3
        move, _ = engine._resolve_move(state, player, MovementDecision(False, ()))
        self.assertEqual(move, 3)

    def test_assassin_clears_marks_and_blocks_future_marks(self):
        policy = TargetPolicy(target_name="아전")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        assassin = state.players[0]
        target = state.players[1]
        bandit = state.players[2]
        assassin.current_character = "자객"
        target.current_character = "아전"
        state.active_by_card[4] = "아전"
        bandit.current_character = "산적"
        target.pending_marks.append({"type": "bandit_tax", "source_pid": bandit.player_id})

        engine._apply_character_start(state, assassin)
        self.assertEqual(target.pending_marks, [])
        self.assertTrue(target.skipped_turn)
        self.assertTrue(target.revealed_this_round)

        engine._queue_mark(state, bandit.player_id, "아전", {"type": "bandit_tax"})
        self.assertEqual(target.pending_marks, [])

    def _legacy_test_mark_target_must_be_future_turn_character(self):
        policy = TargetPolicy(target_name="아전")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        assassin = state.players[0]
        earlier = state.players[1]
        later = state.players[2]
        assassin.current_character = "자객"
        earlier.current_character = "아전"
        later.current_character = "산적"
        state.current_round_order = [earlier.player_id, assassin.player_id, later.player_id]

        engine._apply_character_start(state, assassin)
        self.assertFalse(earlier.skipped_turn)
        self.assertFalse(earlier.revealed_this_round)
        self.assertEqual(engine._strategy_stats[assassin.player_id]["mark_attempts"], 1)
        self.assertEqual(engine._strategy_stats[assassin.player_id].get("mark_successes", 0), 0)
        self.assertEqual(engine._strategy_stats[assassin.player_id].get("mark_fail_missing", 0), 1)

    def test_mark_target_must_be_future_turn_character(self):
        requested_target = CARD_TO_NAMES[1][1]
        policy = TargetPolicy(target_name=requested_target)
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        assassin = state.players[0]
        earlier = state.players[1]
        later = state.players[2]
        assassin.current_character = CARD_TO_NAMES[2][0]
        earlier.current_character = requested_target
        later.current_character = CARD_TO_NAMES[6][0]
        state.current_round_order = [earlier.player_id, assassin.player_id, later.player_id]

        engine._apply_character_start(state, assassin)
        self.assertFalse(earlier.skipped_turn)
        self.assertFalse(earlier.revealed_this_round)
        self.assertTrue(later.skipped_turn)
        self.assertTrue(later.revealed_this_round)
        self.assertEqual(engine._strategy_stats[assassin.player_id]["mark_attempts"], 1)
        self.assertEqual(engine._strategy_stats[assassin.player_id].get("mark_successes", 0), 1)
        self.assertEqual(engine._strategy_stats[assassin.player_id].get("mark_fail_missing", 0), 0)

    def test_mark_target_none_is_coerced_when_legal_target_exists(self):
        policy = TargetPolicy(target_name=None)
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        actor = state.players[0]
        first_target = state.players[1]
        second_target = state.players[2]
        actor.current_character = CARD_TO_NAMES[2][1]  # bandit
        first_target.current_character = CARD_TO_NAMES[4][0]
        second_target.current_character = CARD_TO_NAMES[6][0]
        state.current_round_order = [actor.player_id, first_target.player_id, second_target.player_id]

        engine._apply_character_start(state, actor)

        self.assertEqual(len(first_target.pending_marks), 1)
        self.assertEqual(first_target.pending_marks[0]["source_pid"], actor.player_id)
        self.assertEqual(first_target.pending_marks[0]["type"], "bandit_tax")
        self.assertEqual(engine._strategy_stats[actor.player_id].get("mark_successes", 0), 1)
        self.assertTrue(any(row.get("event") == "mark_target_coerced" for row in engine._action_log))

    def test_mark_target_invalid_choice_is_coerced_to_first_future_target(self):
        requested_target = CARD_TO_NAMES[1][1]
        policy = TargetPolicy(target_name=requested_target)
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        earlier = state.players[0]
        actor = state.players[1]
        later = state.players[2]
        earlier.current_character = requested_target
        actor.current_character = CARD_TO_NAMES[2][1]  # bandit
        later.current_character = CARD_TO_NAMES[3][0]
        state.current_round_order = [earlier.player_id, actor.player_id, later.player_id]

        engine._apply_character_start(state, actor)

        self.assertEqual(len(earlier.pending_marks), 0)
        self.assertEqual(len(later.pending_marks), 1)
        self.assertEqual(later.pending_marks[0]["source_pid"], actor.player_id)
        self.assertEqual(later.pending_marks[0]["type"], "bandit_tax")

    def test_mark_target_coercion_uses_future_public_active_faces(self):
        requested_target = CARD_TO_NAMES[1][1]
        policy = TargetPolicy(target_name=requested_target)
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        actor = state.players[0]
        future_one = state.players[1]
        future_two = state.players[2]

        actor.current_character = CARD_TO_NAMES[2][0]  # 자객
        future_one.current_character = CARD_TO_NAMES[7][0]  # 객주
        future_two.current_character = CARD_TO_NAMES[8][0]  # 건설업자
        state.active_by_card[7] = CARD_TO_NAMES[7][1]  # 중매꾼
        state.active_by_card[8] = CARD_TO_NAMES[8][1]  # 사기꾼
        state.current_round_order = [actor.player_id, future_one.player_id, future_two.player_id]

        engine._apply_character_start(state, actor)

        self.assertEqual(len(future_one.pending_marks), 0)
        self.assertEqual(len(future_two.pending_marks), 0)
        coerced = next((row for row in engine._action_log if row.get("event") == "mark_target_coerced"), None)
        self.assertIsNotNone(coerced)
        self.assertEqual(coerced["target_character"], CARD_TO_NAMES[7][1])

    def test_mark_target_explicit_unheld_public_face_resolves_as_miss(self):
        requested_target = CARD_TO_NAMES[3][1]
        policy = TargetPolicy(target_name=requested_target)
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        actor = state.players[0]
        future_one = state.players[1]
        future_two = state.players[2]

        actor.current_character = CARD_TO_NAMES[2][0]  # 자객
        future_one.current_character = CARD_TO_NAMES[7][0]  # 객주
        future_two.current_character = CARD_TO_NAMES[8][0]  # 건설업자
        state.active_by_card[3] = CARD_TO_NAMES[3][1]  # 탈출 노비 (unheld public face)
        state.active_by_card[7] = CARD_TO_NAMES[7][1]  # 중매꾼
        state.active_by_card[8] = CARD_TO_NAMES[8][1]  # 사기꾼
        state.current_round_order = [actor.player_id, future_one.player_id, future_two.player_id]

        engine._apply_character_start(state, actor)

        self.assertFalse(future_one.skipped_turn)
        self.assertFalse(future_two.skipped_turn)
        self.assertEqual(engine._strategy_stats[actor.player_id].get("mark_fail_missing", 0), 1)

    def test_mark_target_visible_candidates_match_shared_player_fixture_metadata(self):
        fixture = _load_selector_player_fixture()
        metadata = fixture["metadata"]

        engine = self.make_engine(policy=DummyPolicy())
        state = self.make_state(engine)
        actor = state.players[0]
        first_target = state.players[1]
        second_target = state.players[2]
        third_target = state.players[3]

        actor.current_character = metadata["actor_character"]
        first_target.current_character = CARD_TO_NAMES[3][0]
        second_target.current_character = CARD_TO_NAMES[4][0]
        third_target.current_character = CARD_TO_NAMES[5][0]
        state.current_round_order = [actor.player_id, first_target.player_id, second_target.player_id, third_target.player_id]
        state.active_by_card[3] = metadata["expected_visible_target_characters"][0]
        state.active_by_card[4] = metadata["expected_visible_target_characters"][1]
        state.active_by_card[5] = metadata["expected_visible_target_characters"][2]

        self.assertEqual(
            ordered_public_mark_targets(state, actor)[:3],
            [
                {"card_no": 3, "target_character": metadata["expected_visible_target_characters"][0]},
                {"card_no": 4, "target_character": metadata["expected_visible_target_characters"][1]},
                {"card_no": 5, "target_character": metadata["expected_visible_target_characters"][2]},
            ],
        )

    def test_malicious_tile_cost_uses_face_value_times_three(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 20
        land_positions = state.tile_positions(land_only=True)
        expected_by_pos = {
            land_positions[0]: 15,
            land_positions[1]: 15,
            land_positions[3]: 12,
        }
        for pos, expected in expected_by_pos.items():
            with self.subTest(pos=pos, expected=expected):
                player.position = pos
                state.board[pos] = CellKind.MALICIOUS
                before = player.cash
                result = engine._resolve_landing(state, player)
                self.assertEqual(result["type"], "MALICIOUS")
                self.assertEqual(result["face_value"], expected // 3)
                self.assertEqual(result["multiplier"], 3)
                self.assertEqual(result["cost"], expected)
                self.assertTrue(result["paid"])
                self.assertEqual(player.cash, before - expected)
                player.cash = 20



    def test_purchase_policy_skips_when_cash_below_estimated_one_turn_risk(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 10
        player.position = 0
        # populate public active threats and a dangerous enemy rent map
        state.active_by_card = {1: "산적", 2: "추노꾼", 3: "객주", 4: "박수", 5: "교리 연구관", 6: "만신", 7: "중매꾼", 8: "사기꾼"}
        state.players[1].current_character = "산적"
        state.players[1].shards = 6
        state.players[2].current_character = "추노꾼"
        threat_lands = state.tile_positions(land_only=True)
        state.tile_owner[threat_lands[3]] = state.players[1].player_id
        state.tile_owner[threat_lands[4]] = state.players[2].player_id
        state.tile_owner[threat_lands[6]] = state.players[1].player_id
        decision = policy.choose_purchase_tile(state, player, threat_lands[1], state.board[threat_lands[1]], 5, source="landing_purchase")
        self.assertFalse(decision)

    def test_purchase_policy_allows_when_cash_buffer_remains_healthy(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 50
        player.position = 0
        state.active_by_card = {1: "산적", 2: "추노꾼", 3: "객주", 4: "박수", 5: "교리 연구관", 6: "만신", 7: "중매꾼", 8: "사기꾼"}
        state.players[1].current_character = "산적"
        state.players[1].shards = 4
        state.players[2].current_character = "추노꾼"
        threat_lands = state.tile_positions(land_only=True)
        state.tile_owner[threat_lands[3]] = state.players[1].player_id
        state.tile_owner[threat_lands[4]] = state.players[2].player_id
        decision = policy.choose_purchase_tile(state, player, threat_lands[1], state.board[threat_lands[1]], 5, source="landing_purchase")
        self.assertTrue(decision)

    def test_initial_active_faces_randomized_deterministically(self):
        state_a = GameState.create(DEFAULT_CONFIG)
        state_b = GameState.create(DEFAULT_CONFIG)
        engine_a = self.make_engine(rng=random.Random(123))
        engine_b = self.make_engine(rng=random.Random(123))
        engine_a._initialize_active_faces(state_a)
        engine_b._initialize_active_faces(state_b)
        self.assertEqual(state_a.active_by_card, state_b.active_by_card)
        self.assertEqual(set(state_a.active_by_card.keys()), set(CARD_TO_NAMES.keys()))
        for card_no, active_name in state_a.active_by_card.items():
            self.assertIn(active_name, CARD_TO_NAMES[card_no])

    def test_mark_risk_penalizes_targetable_late_characters_in_v1_and_v2(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = DEFAULT_CONFIG.economy.starting_cash
        state.active_by_card = {
            1: "어사",
            2: "산적",
            3: "추노꾼",
            4: "아전",
            5: "교리 연구관",
            6: "박수",
            7: "객주",
            8: "사기꾼",
        }

        safe_state = GameState.create(DEFAULT_CONFIG)
        safe_player = safe_state.players[0]
        safe_player.cash = DEFAULT_CONFIG.economy.starting_cash
        safe_state.active_by_card = {
            1: "어사",
            2: "탈출 노비",
            3: "파발꾼",
            4: "아전",
            5: "교리 연구관",
            6: "교리 감독관",
            7: "객주",
            8: "건설업자",
        }

        v1 = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        risky_v1, _ = v1._character_score_breakdown(state, player, "중매꾼")
        safe_v1, _ = v1._character_score_breakdown(safe_state, safe_player, "중매꾼")
        self.assertLess(risky_v1, safe_v1)

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        risky_v2, _ = v2._character_score_breakdown_v2(state, player, "중매꾼")
        safe_v2, _ = v2._character_score_breakdown_v2(safe_state, safe_player, "중매꾼")
        self.assertLess(risky_v2, safe_v2)

    def test_rent_pressure_prefers_escape_characters_in_v1_and_v2(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.position = 0
        player.cash = 5
        state.active_by_card = {
            1: "중매꾼",
            2: "파발꾼",
            3: "건설업자",
            4: "탈출 노비",
            5: "객주",
            6: "교리 연구관",
            7: "어사",
            8: "아전",
        }
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        v1 = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertEqual(v1.choose_final_character(state, player, [1, 2]), "파발꾼")
        self.assertEqual(v1.choose_final_character(state, player, [3, 4]), "탈출 노비")

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertEqual(v2.choose_final_character(state, player, [1, 2]), "파발꾼")
        self.assertEqual(v2.choose_final_character(state, player, [3, 4]), "탈출 노비")

    def test_survival_gate_rejects_growth_character_when_broke(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.position = 0
        player.cash = 1
        state.active_by_card = {
            1: "중매꾼",
            2: "탈출 노비",
            3: "건설업자",
            4: "자객",
            5: "객주",
            6: "사기꾼",
            7: "파발꾼",
            8: "아전",
        }
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_growth", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertEqual(v2.choose_final_character(state, player, [1, 2]), "탈출 노비")
        self.assertEqual(v2.choose_final_character(state, player, [3, 4]), "자객")

    def test_survival_lap_reward_forces_cash_even_in_growth_profile(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "중매꾼"
        player.cash = 2
        player.hand_coins = 2
        player.position = 0
        land_pos = first_land_positions(state)[0]
        state.tile_owner[land_pos] = player.player_id
        state.tile_coins[land_pos] = 1
        player.tiles_owned = 1
        player.visited_owned_tile_indices = {land_pos}
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_growth")
        self.assertEqual(policy.choose_lap_reward(state, player).choice, "cash")

    def test_survival_trick_prefers_rent_relief_over_growth_trick(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 2
        player.position = 0
        health = next(card for card in state.trick_draw_pile if card.name == "건강 검진")
        free_gift = next(card for card in state.trick_draw_pile if card.name == "무료 증정")
        player.trick_hand = [health, free_gift]
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_growth", rng=random.Random(0))
        self.assertEqual(policy.choose_trick_to_use(state, player, player.trick_hand).name, "건강 검진")

    def test_nonleader_survival_movement_does_not_spend_cards_to_hit_f_tile(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 2
        player.current_character = "중매꾼"
        player.position = 7
        player.used_dice_cards = {3, 4, 5, 6}
        for pos in [1, 2, 3, 4, 5, 6]:
            if state.board[pos] in {CellKind.T2, CellKind.T3}:
                state.tile_owner[pos] = state.players[1].player_id
                state.players[1].tiles_owned += 1

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_growth", rng=random.Random(0))
        policy._landing_score = lambda state, player, pos: 0.0
        decision = policy.choose_movement(state, player)

        self.assertFalse(decision.use_cards)

    def test_leader_finish_movement_can_spend_cards_to_hit_f_tile(self):
        state = GameState.create(DEFAULT_CONFIG)
        state.f_value = 12
        player = state.players[0]
        player.cash = 10
        player.current_character = "중매꾼"
        player.position = 7
        player.used_dice_cards = {3, 4, 5, 6}
        player.tiles_owned = 5
        for pos in [11, 12, 13]:
            if state.board[pos] in {CellKind.T2, CellKind.T3}:
                state.tile_owner[pos] = player.player_id
        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_growth", rng=random.Random(0))
        policy._landing_score = lambda state, player, pos: 0.0
        decision = policy.choose_movement(state, player)

        self.assertTrue(decision.use_cards)
        self.assertEqual(sum(decision.card_values), 3)


    def test_nonleader_geo_bonus_prefers_cash_over_f_progress_rewards(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 8
        player.current_character = "객주"
        for pos in [1, 2, 3, 4, 5, 6]:
            if state.board[pos] in {CellKind.T2, CellKind.T3}:
                state.tile_owner[pos] = state.players[1].player_id
                state.players[1].tiles_owned += 1
        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced", lap_policy_mode="heuristic_v2_balanced")
        self.assertEqual(policy.choose_geo_bonus(state, player, player.current_character), "cash")

    def test_end_rule_triggers_three_monopolies(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.alive = True
        monopoly_blocks = [1, 2, 3]
        for block_id in monopoly_blocks:
            idxs = [i for i, b in enumerate(state.block_ids) if b == block_id]
            for idx in idxs:
                state.tile_owner[idx] = player.player_id
            player.tiles_owned += len(idxs)
        self.assertTrue(engine._check_end(state))
        self.assertEqual(state.end_reason, "THREE_MONOPOLIES")


    def test_trick_visibility_reveals_all_but_one(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine._draw_tricks(state, player, 5)
        self.assertEqual(len(player.trick_hand), 5)
        self.assertEqual(player.hidden_trick_count(), 1)
        self.assertEqual(len(player.public_trick_cards()), 4)
        hidden_ids = {c.deck_index for c in player.trick_hand} - {c.deck_index for c in player.public_trick_cards()}
        self.assertEqual(hidden_ids, {player.hidden_trick_deck_index})

    def test_hidden_trick_is_preserved_until_removed(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine._draw_tricks(state, player, 3)
        hidden_before = player.hidden_trick_deck_index
        public_card = next(c for c in player.trick_hand if c.deck_index != hidden_before)
        engine._remove_trick_from_hand(state, player, public_card)
        self.assertEqual(player.hidden_trick_deck_index, hidden_before)
        hidden_card = next(c for c in player.trick_hand if c.deck_index == hidden_before)
        engine._remove_trick_from_hand(state, player, hidden_card)
        self.assertEqual(player.hidden_trick_count(), 1)
        self.assertIsNotNone(player.hidden_trick_deck_index)
        self.assertNotEqual(player.hidden_trick_deck_index, hidden_before)

    def test_opponent_trick_inference_uses_only_public_cards(self):
        policy = HeuristicPolicy()
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        viewer = state.players[0]
        target = state.players[1]
        burden = next(c for c in state.trick_draw_pile if c.name == "무거운 짐")
        free_gift = next(c for c in state.trick_draw_pile if c.name == "무료 증정")
        health = next(c for c in state.trick_draw_pile if c.name == "건강 검진")
        target.trick_hand = [burden, free_gift, health]
        engine._sync_trick_visibility(state, target)
        hidden = next(c for c in target.trick_hand if c.name == "무거운 짐")
        target.hidden_trick_deck_index = hidden.deck_index
        tags = policy._predicted_opponent_archetypes(state, viewer, target)
        self.assertNotIn("burden", tags)
        self.assertIn("combo_ready", tags)
        target.hidden_trick_deck_index = next(c for c in target.trick_hand if c.name == "무료 증정").deck_index
        tags = policy._predicted_opponent_archetypes(state, viewer, target)
        self.assertIn("burden", tags)
        self.assertNotIn("combo_ready", tags)


    def test_baksu_score_rises_when_future_burden_cleanup_risk_is_high(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v1")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        player = state.players[0]
        player.current_character = "아전"
        for idx, target in enumerate(state.players[1:], start=1):
            target.current_character = list(CARD_TO_NAMES[idx])[0]
        base_score, _ = policy._character_score_breakdown(state, player, "박수")
        burden_cards = [c for c in state.trick_draw_pile if c.name in {"무거운 짐", "가벼운 짐"}][:2]
        player.trick_hand = burden_cards
        enriched_score, _ = policy._character_score_breakdown(state, player, "박수")
        self.assertGreater(enriched_score, base_score + 2.0)


    def test_cleanup_deck_profile_tracks_fire_and_wildfire_remaining(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v1")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        profile = policy._fortune_cleanup_deck_profile(state)
        self.assertGreaterEqual(profile["remaining_fire_count"], 0.0)
        self.assertGreaterEqual(profile["remaining_wildfire_count"], 0.0)
        self.assertGreater(profile["remaining_draws"], 0.0)
        self.assertGreaterEqual(profile["cycle_cleanup_prob"], profile["next_draw_cleanup_prob"])
        state.fortune_discard_pile.extend([c for c in state.fortune_draw_pile if getattr(c, "name", "") in {"화재 발생", "산불 발생"}])
        state.fortune_draw_pile = [c for c in state.fortune_draw_pile if getattr(c, "name", "") not in {"화재 발생", "산불 발생"}]
        profile2 = policy._fortune_cleanup_deck_profile(state)
        self.assertEqual(profile2["remaining_negative_cleanup_cards"], 0.0)
        self.assertEqual(profile2["next_draw_negative_cleanup_prob"], 0.0)
        self.assertGreater(profile2["cycle_cleanup_prob"], 0.0)
        self.assertGreaterEqual(profile2["two_draw_cleanup_prob"], 0.0)

    def test_end_turn_cleanup_pressure_keeps_probabilistic_cleanup_risk(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v1")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        player = state.players[0]
        burdens = [c for c in state.trick_draw_pile if c.name in {"가벼운 짐", "무거운 짐"}][:2]
        player.trick_hand = burdens
        player.cash = 6
        pressure = policy._end_turn_cleanup_pressure(state, player, projected_cash=6)
        self.assertGreater(pressure["cycle_cleanup_prob"], 0.0)
        self.assertGreaterEqual(pressure["downside_expected_cleanup_cost"], pressure["immediate_cleanup_cost"])
        self.assertGreaterEqual(pressure["projected_cleanup_lethal"], 0.0)

    def test_fire_fortune_cleanup_uses_one_x_multiplier(self):
        policy = DummyPolicy()
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        player = state.players[0]
        light = next(c for c in state.trick_draw_pile if c.name == "가벼운 짐")
        player.trick_hand = [light]
        player.cash = 5
        result = engine._apply_fortune_card_impl(state, player, FortuneCard(deck_index=999, name="화재 발생", effect=""))
        self.assertEqual(result["type"], "BURDEN_CLEANUP")
        self.assertEqual(player.cash, 3)

    def test_manshin_score_rises_with_visible_public_burdens(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        player = state.players[0]
        player.current_character = "아전"
        for idx, target in enumerate(state.players[1:], start=1):
            target.current_character = list(CARD_TO_NAMES[idx])[0]
        base_score, _ = policy._character_score_breakdown_v2(state, player, "만신")
        burden = next(c for c in state.trick_draw_pile if c.name == "무거운 짐")
        filler = next(c for c in state.trick_draw_pile if c.name == "무료 증정")
        target = state.players[1]
        target.cash = 8
        target.trick_hand = [burden, filler]
        target.hidden_trick_deck_index = filler.deck_index
        enriched_score, _ = policy._character_score_breakdown_v2(state, player, "만신")
        self.assertGreater(enriched_score, base_score + 2.0)


class TrickSystemTests(unittest.TestCase):
    def make_engine(self, policy=None, rng=None):
        return GameEngine(DEFAULT_CONFIG, policy or DummyPolicy(), rng=rng or random.Random(0), enable_logging=True)

    def make_state(self, engine):
        state = GameState.create(DEFAULT_CONFIG)
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        return state

    def test_manshin_removes_burdens_and_collects_cost(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        manshin = state.players[0]
        target = state.players[1]
        manshin.current_character = "만신"
        target.current_character = "아전"
        target.cash = 20
        target.trick_hand = [c for c in state.trick_draw_pile if c.name in {"무거운 짐","가벼운 짐"}][:2]
        for c in target.trick_hand:
            state.trick_draw_pile = [x for x in state.trick_draw_pile if x.deck_index != c.deck_index]
        total_remove_cost = sum(c.burden_cost for c in target.trick_hand)
        target.pending_marks.append({"type": "manshin_remove_burdens", "source_pid": manshin.player_id})
        engine._resolve_pending_marks(state, target)
        self.assertEqual(target.cash, 20 - total_remove_cost)
        self.assertEqual(manshin.cash, DEFAULT_CONFIG.economy.starting_cash + total_remove_cost)
        self.assertEqual(len(target.trick_hand), 0)
    def test_weather_hunt_season_gives_muroe_mark_bonus_cash(self):
        policy = TargetPolicy(target_name="아전")
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        state.current_weather_effects = {"사냥의 계절"}
        bandit = state.players[0]
        target = state.players[1]
        bandit.current_character = "산적"
        target.current_character = "아전"
        state.active_by_card[4] = "아전"
        start_cash = bandit.cash
        engine._apply_character_start(state, bandit)
        self.assertEqual(engine._strategy_stats[bandit.player_id]["mark_successes"], 1)
        self.assertEqual(bandit.cash, start_cash + 4)

    def test_weather_cold_winter_blocks_lap_reward_and_charges_cash(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        state.current_weather_effects = {"추운 겨울날"}
        player = state.players[0]
        player.cash = 10
        event = engine._apply_lap_reward(state, player)
        self.assertEqual(event["choice"], "blocked_by_weather")
        self.assertEqual(player.cash, 8)

    def test_weather_color_rent_double_by_block_color(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        state.current_weather_effects = {"검은 달"}
        owner = state.players[1]
        player = state.players[0]
        owner.current_character = "아전"
        player.current_character = "객주"
        pos = 1
        self.assertEqual(state.block_color_map[state.block_ids[pos]], "검은색")
        state.tile_owner[pos] = owner.player_id
        owner.tiles_owned = 1
        player.position = pos
        event = engine._resolve_landing(state, player)
        self.assertEqual(event["type"], "RENT")
        self.assertEqual(event["rent"], DEFAULT_CONFIG.economy.rent_cost_for(state.board, pos) * 2)

    def test_weather_same_tile_bonus_applies(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        state.current_weather_effects = {"사랑과 우정"}
        player = state.players[0]
        other1 = state.players[1]
        other2 = state.players[2]
        player.current_character = "객주"
        other1.current_character = "아전"
        other2.current_character = "산적"
        state.players[3].position = 5
        player.position = other1.position = other2.position = 0
        event = engine._resolve_landing(state, player)
        self.assertEqual(event["weather_same_tile_cash_gain"], 8)

    def test_weather_disputed_ownerless_land_charges_bank_before_purchase(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        state.current_weather_effects = {"대규모 민란"}
        player = state.players[0]
        player.current_character = "객주"
        player.position = 1
        player.cash = 20
        event = engine._resolve_landing(state, player)
        self.assertEqual(event["type"], "PURCHASE")
        self.assertEqual(event["weather_disputed_rent"]["rent"], DEFAULT_CONFIG.economy.rent_cost_for(state.board, 1))
        self.assertEqual(player.cash, 20 - DEFAULT_CONFIG.economy.rent_cost_for(state.board, 1) - DEFAULT_CONFIG.economy.purchase_cost_for(state.board, 1))


    def test_distress_without_escape_option_prefers_marker_controller(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 5
        player.position = 0
        player.trick_hand = [next(card for card in state.trick_draw_pile if card.name == "무거운 짐")]
        state.active_by_card = {
            1: "중매꾼",
            2: "건설업자",
            3: "교리 연구관",
            4: "사기꾼",
            5: "어사",
            6: "아전",
            7: "객주",
            8: "교리 감독관",
        }
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        v1 = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertIn(v1.choose_final_character(state, player, [1, 3]), {"교리 연구관"})

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertIn(v2.choose_final_character(state, player, [1, 3]), {"교리 연구관"})

    def test_burden_exchange_is_declined_under_escape_seek_pressure(self):
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 6
        player.position = 0
        burden_card = next(card for card in state.trick_draw_pile if card.name == "무거운 짐")
        player.trick_hand = [burden_card]
        state.active_by_card = {
            1: "중매꾼",
            2: "건설업자",
            3: "교리 연구관",
            4: "사기꾼",
            5: "어사",
            6: "아전",
            7: "객주",
            8: "교리 감독관",
        }
        for pos in [2, 3, 5, 6, 8, 9, 10]:
            owner = 1 if pos % 2 == 0 else 2
            state.tile_owner[pos] = owner
            state.players[owner].tiles_owned += 1

        v1 = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertFalse(v1.choose_burden_exchange_on_supply(state, player, burden_card))

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced", lap_policy_mode="heuristic_v1", rng=random.Random(0))
        self.assertFalse(v2.choose_burden_exchange_on_supply(state, player, burden_card))

    def test_end_rule_triggers_nine_tiles_without_auto_win_override(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        tile_leader = state.players[0]
        score_leader = state.players[1]
        tile_leader.tiles_owned = 9
        score_leader.tiles_owned = 5
        score_leader.score_coins_placed = 5

        self.assertTrue(engine._check_end(state))
        self.assertEqual(state.end_reason, "NINE_TILES")
        self.assertEqual(state.winner_ids, [score_leader.player_id])

    def test_round_flow_reveals_weather_before_draft(self):
        class RoundFlowPolicy(DummyPolicy):
            def choose_final_character(self, state, player, card_choices):
                return state.active_by_card[card_choices[0]]

        policy = RoundFlowPolicy()
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        engine._initialize_active_faces(state)
        engine._start_new_round(state, initial=True)

        timeline = [
            row.get("event")
            for row in engine._action_log
            if row.get("event") in {"weather_round", "draft_pick"}
        ]
        self.assertIn("weather_round", timeline)
        self.assertIn("draft_pick", timeline)
        self.assertLess(timeline.index("weather_round"), timeline.index("draft_pick"))

    def test_four_player_second_draft_is_random_assignment(self):
        class CountingDraftPolicy(DummyPolicy):
            def __init__(self):
                super().__init__()
                self.draft_calls = 0

            def choose_draft_card(self, state, player, offered_cards):
                self.draft_calls += 1
                return offered_cards[0]

            def choose_final_character(self, state, player, card_choices):
                return state.active_by_card[card_choices[0]]

        policy = CountingDraftPolicy()
        engine = self.make_engine(policy=policy)
        state = self.make_state(engine)
        engine._initialize_active_faces(state)
        engine._run_draft(state)

        self.assertEqual(policy.draft_calls, DEFAULT_CONFIG.player_count)
        self.assertTrue(all(len(p.drafted_cards) == 2 for p in state.players))
        phase2 = [
            row
            for row in engine._action_log
            if row.get("event") == "draft_pick" and row.get("phase") == 2
        ]
        self.assertEqual(len(phase2), DEFAULT_CONFIG.player_count)
        self.assertTrue(all(row.get("random_assigned", False) for row in phase2))

    def test_marker_management_moves_owner_to_doctrine_player_at_round_end(self):
        engine = self.make_engine(policy=DummyPolicy())
        state = self.make_state(engine)
        state.marker_owner_id = 1
        state.marker_draft_clockwise = False
        player = state.players[0]
        player.current_character = "교리 연구관"

        engine._apply_marker_management(state, player)

        self.assertEqual(state.marker_owner_id, player.player_id)
        self.assertFalse(state.marker_draft_clockwise)
        self.assertEqual(state.pending_marker_flip_owner_id, player.player_id)
        marker_event = next(
            row for row in reversed(engine._action_log) if row.get("event") == "marker_moved"
        )
        self.assertTrue(marker_event.get("marker_changed", False))

    def test_marker_flip_batch_finishes_with_one_decision(self):
        class BatchFlipPolicy(DummyPolicy):
            def choose_active_flip_card(self, state, player, flippable_cards):
                del state, player, flippable_cards
                return [0, 1]

        engine = self.make_engine(policy=BatchFlipPolicy())
        state = self.make_state(engine)
        state.pending_marker_flip_owner_id = 0
        state.marker_owner_id = 0
        state.active_by_card = {0: CARD_TO_NAMES[0][0], 1: CARD_TO_NAMES[1][0]}

        result = engine.effect_handlers.handle_marker_flip(state)

        self.assertEqual(state.pending_marker_flip_owner_id, None)
        self.assertEqual(result["event"], "marker_flip_sequence")
        self.assertEqual(result["cards"], [0, 1])
        flip_rows = [row for row in engine._action_log if row.get("event") == "marker_flip"]
        self.assertEqual([row.get("card_no") for row in flip_rows[-2:]], [0, 1])

    def test_trick_phase_uses_only_one_card_per_turn(self):
        class FirstUsablePolicy(DummyPolicy):
            def choose_trick_to_use(self, state, player, hand):
                return hand[0] if hand else None

        engine = self.make_engine(policy=FirstUsablePolicy())
        state = self.make_state(engine)
        player = state.players[0]
        usable = [
            card
            for card in build_trick_deck()
            if card.name not in {"무거운 짐", "가벼운 짐"}
        ]
        player.trick_hand = [usable[0], usable[1]]
        engine._strategy_stats[player.player_id].update(
            {"tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0}
        )

        engine._use_trick_phase(state, player)

        self.assertEqual(len(player.trick_hand), 1)
        stats = engine._strategy_stats[player.player_id]
        self.assertEqual(stats["tricks_used"], 1)
        self.assertEqual(stats["regular_tricks_used"], 1)
        self.assertEqual(stats["anytime_tricks_used"], 0)
        trick_events = [
            row
            for row in engine._action_log
            if row.get("event") == "trick_used" and row.get("player") == player.player_id + 1
        ]
        self.assertEqual(len(trick_events), 1)

    def test_hogaekkun_slowdown_reduces_effective_move_when_crossed(self):
        engine = self.make_engine(policy=DummyPolicy())
        state = self.make_state(engine)
        blocker = state.players[0]
        mover = state.players[1]
        blocker.trick_obstacle_this_round = True
        blocker.position = 2
        mover.position = 0
        mover.total_steps = 0

        engine._advance_player(state, mover, 4, {"mode": "test"})

        self.assertEqual(mover.position, 3)
        turn_row = next(row for row in reversed(engine._action_log) if row.get("event") == "turn")
        slowdown = turn_row.get("obstacle_slowdown")
        self.assertIsNotNone(slowdown)
        self.assertEqual(slowdown.get("planned_move"), 4)
        self.assertEqual(slowdown.get("effective_move"), 3)
        self.assertEqual(slowdown.get("reduced_by"), 1)

    def test_vis_stream_emits_player_move_before_landing_and_rent(self):
        fixture = _load_selector_scene_fixture()
        expected_order = fixture["metadata"]["engine_advance_resolution_order"]
        stream = VisEventStream()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True, event_stream=stream)
        state = self.make_state(engine)
        mover = state.players[0]
        owner = state.players[1]
        rent_tile = first_t3_position(state)
        mover.position = (rent_tile - 1) % len(state.board)
        mover.total_steps = mover.position
        owner.position = rent_tile
        owner.total_steps = owner.position
        owner.tiles_owned = 1
        state.tile_owner[rent_tile] = owner.player_id
        state.current_round_order = [mover.player_id, owner.player_id]
        state.turn_index = 0
        engine._vis_session_id = "test-session"

        engine._advance_player(state, mover, 1, {"mode": "test", "formula": "1"})

        event_types = [event.event_type for event in stream.events]
        for event_code in expected_order:
            self.assertIn(event_code, event_types)
        for before, after in zip(expected_order, expected_order[1:]):
            self.assertLess(event_types.index(before), event_types.index(after))

    def test_reroll_cards_are_consumed_by_trick_phase_selection(self):
        class RerollPolicy(DummyPolicy):
            def choose_trick_to_use(self, state, player, hand):
                for card in hand:
                    if card.name == "뭔칙휜":
                        return card
                return hand[0] if hand else None

        engine = self.make_engine(policy=RerollPolicy())
        state = self.make_state(engine)
        player = state.players[0]
        deck = build_trick_deck()
        reroll = next(card for card in deck if card.name == "뭔칙휜")
        filler = next(card for card in deck if card.name not in {"뭔칙휜", "무거운 짐", "가벼운 짐"})
        player.trick_hand = [reroll, filler]
        engine._strategy_stats[player.player_id].update(
            {"tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0}
        )

        engine._use_trick_phase(state, player)

        self.assertEqual(player.trick_reroll_budget_this_turn, 2)
        self.assertEqual(player.trick_reroll_label_this_turn, "뭔칙휜")
        self.assertEqual(len(player.trick_hand), 1)

    def test_reroll_budget_does_not_consume_extra_trick_cards(self):
        engine = self.make_engine(policy=DummyPolicy())
        state = self.make_state(engine)
        player = state.players[0]
        player.trick_reroll_budget_this_turn = 2
        player.trick_reroll_label_this_turn = "뭔칙휜"
        engine.policy._landing_score = lambda *_args, **_kwargs: 0.0

        _, rerolls = engine._try_anytime_rerolls(
            state,
            player,
            used_cards=[],
            dice=[1, 1],
            mode="dice",
        )

        self.assertEqual(len(rerolls), 2)
        self.assertTrue(all(item.get("card") == "뭔칙휜" for item in rerolls))



    def test_change_f_clamps_to_zero_and_logs_reason(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        state.f_value = 1
        engine._change_f(state, -3, reason="unit_test", source="negative_probe", actor_pid=state.players[0].player_id)
        self.assertEqual(state.f_value, 0)
        event = next(e for e in reversed(engine._action_log) if e.get("event") == "resource_f_change")
        self.assertEqual(event["before"], 1)
        self.assertEqual(event["requested_delta"], -3)
        self.assertEqual(event["delta"], -1)
        self.assertTrue(event["clamped"])
        self.assertEqual(event["reason"], "unit_test")
        self.assertEqual(event["source"], "negative_probe")


class ChunkMergeForensicsTests(unittest.TestCase):
    def test_merge_chunks_restores_missing_chunk_metadata_and_unique_game_ids(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        from run_chunked_batch import _merge_chunks
        from simulate_with_logs import RunningSummary

        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                chunk1 = root / "chunk_001"
                chunk2 = root / "chunk_003"
                chunk1.mkdir()
                chunk2.mkdir()
                row1 = {
                "game_id": 0,
                "global_game_index": 0,
                "turns": 10,
                "total_turns": 10,
                "rounds": 3,
                "rounds_completed": 3,
                "end_reason": "ALIVE_THRESHOLD",
                "winner_ids": [1],
                "player_summary": [],
                "strategy_summary": [],
                "f_value": 4,
                "final_f_value": 4,
                "total_placed_coins": 0,
                "bankrupt_players": 0,
                "integrity": {"ok": True, "mismatches": []},
                "policy_mode": "arena",
                "lap_policy_mode": "heuristic_v1",
                "player_lap_policy_modes": {},
                "player_character_policy_modes": {},
                "bankruptcy_events": [],
                "weather_history": [],
            }
                row2 = {
                "game_id": 0,
                "turns": 11,
                "total_turns": 11,
                "rounds": 3,
                "rounds_completed": 3,
                "end_reason": "F_THRESHOLD",
                "winner_ids": [2],
                "player_summary": [],
                "strategy_summary": [],
                "f_value": 6,
                "final_f_value": 6,
                "total_placed_coins": 0,
                "bankrupt_players": 0,
                "integrity": {"ok": True, "mismatches": []},
                "policy_mode": "arena",
                "lap_policy_mode": "heuristic_v1",
                "player_lap_policy_modes": {},
                "player_character_policy_modes": {},
                "bankruptcy_events": [],
                "weather_history": [],
            }
                (chunk1 / "games.jsonl").write_text(json.dumps(row1, ensure_ascii=False) + "\n", encoding="utf-8")
                (chunk2 / "games.jsonl").write_text(json.dumps(row2, ensure_ascii=False) + "\n", encoding="utf-8")
                (chunk1 / "errors.jsonl").write_text("", encoding="utf-8")
                (chunk2 / "errors.jsonl").write_text("", encoding="utf-8")
                running = RunningSummary(
                policy_mode="arena",
                lap_policy_mode="heuristic_v1",
                player_lap_policy_modes={},
                player_character_policy_modes={},
                )
                _merge_chunks(root, running, [chunk1, chunk2])
                rows = [json.loads(line) for line in (root / "games.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                self.assertEqual([row["game_id"] for row in rows], [0, 1])
                self.assertEqual([row["global_game_index"] for row in rows], [0, 1])
                self.assertEqual(rows[0]["chunk_id"], 1)
                self.assertEqual(rows[1]["chunk_id"], 3)
                self.assertEqual(rows[1]["chunk_game_id"], 0)
        except PermissionError as exc:
            self.skipTest(f"Temporary directory permission issue on this environment: {exc}")


class DoctrineBurdenReliefTests(unittest.TestCase):

    def _init_strategy_stats_for_mark_tests(self, engine):
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
    def test_doctrine_relieves_one_own_burden_when_no_team_mode(self):
        cfg = DEFAULT_CONFIG
        engine = GameEngine(cfg, DummyPolicy())
        state = GameState.create(cfg)
        p = state.players[0]
        p.current_character = "교리 연구관"
        p.shards = 8
        p.trick_hand = [TrickCard(0, "무거운 짐", ""), TrickCard(1, "가벼운 짐", "")]
        engine._apply_character_start(state, p)
        self.assertEqual(sorted(c.name for c in p.trick_hand), ["가벼운 짐"])

    def test_doctrine_can_relieves_team_member_when_team_id_present(self):
        cfg = DEFAULT_CONFIG
        engine = GameEngine(cfg, DummyPolicy())
        state = GameState.create(cfg)
        p0 = state.players[0]
        p1 = state.players[1]
        object.__setattr__(p0, "team_id", 1)
        object.__setattr__(p1, "team_id", 1)
        p0.current_character = "교리 감독관"
        p0.shards = 8
        p0.trick_hand = []
        p1.trick_hand = [TrickCard(0, "무거운 짐", "")]
        engine._apply_character_start(state, p0)
        self.assertEqual(len(p1.trick_hand), 0)

    def test_doctrine_does_not_relieve_when_shards_below_eight(self):
        cfg = DEFAULT_CONFIG
        engine = GameEngine(cfg, DummyPolicy())
        state = GameState.create(cfg)
        p = state.players[0]
        p.current_character = "교리 연구관"
        p.shards = 7
        p.trick_hand = [TrickCard(0, "무거운 짐", ""), TrickCard(1, "가벼운 짐", "")]
        engine._apply_character_start(state, p)
        self.assertEqual(len(p.trick_hand), 2)

    def test_baksu_failed_mark_fallback_removes_own_burden_and_gains_cash(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        baksu = state.players[0]
        baksu.current_character = "박수"
        baksu.shards = 6
        burden = next(c for c in state.trick_draw_pile if c.name == "가벼운 짐")
        state.trick_draw_pile = [c for c in state.trick_draw_pile if c.deck_index != burden.deck_index]
        baksu.trick_hand = [burden]
        start_cash = baksu.cash
        engine._queue_mark(state, baksu.player_id, None, {"type": "baksu_transfer"})
        self.assertEqual(len([c for c in baksu.trick_hand if getattr(c, "is_burden", False)]), 0)
        self.assertEqual(baksu.cash, start_cash + burden.burden_cost)

    def test_manshin_failed_mark_fallback_uses_threshold_eight(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        manshin = state.players[0]
        manshin.current_character = "만신"
        manshin.shards = 7
        burden = next(c for c in state.trick_draw_pile if c.name == "무거운 짐")
        state.trick_draw_pile = [c for c in state.trick_draw_pile if c.deck_index != burden.deck_index]
        manshin.trick_hand = [burden]
        start_cash = manshin.cash
        engine._queue_mark(state, manshin.player_id, None, {"type": "manshin_remove_burdens"})
        self.assertEqual(len([c for c in manshin.trick_hand if getattr(c, "is_burden", False)]), 1)
        self.assertEqual(manshin.cash, start_cash)
        manshin.shards = 8
        engine._queue_mark(state, manshin.player_id, None, {"type": "manshin_remove_burdens"})
        self.assertEqual(len([c for c in manshin.trick_hand if getattr(c, "is_burden", False)]), 0)
        self.assertEqual(manshin.cash, start_cash + burden.burden_cost)

    def test_bandit_mark_queue_emits_visibility_event(self):
        policy = TargetPolicy(target_name=CARD_TO_NAMES[4][0])
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        actor = state.players[0]
        target = state.players[1]
        actor.current_character = "산적"
        target.current_character = CARD_TO_NAMES[4][0]
        state.current_round_order = [actor.player_id, target.player_id]

        with patch.object(engine, "_emit_vis") as emit_vis:
            engine._apply_character_start(state, actor)

        self.assertTrue(any(call.args[0] == "mark_queued" for call in emit_vis.call_args_list))

    def test_assassin_mark_success_emits_visibility_event(self):
        policy = TargetPolicy(target_name=CARD_TO_NAMES[4][0])
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        actor = state.players[0]
        target = state.players[1]
        actor.current_character = "자객"
        target.current_character = CARD_TO_NAMES[4][0]
        state.current_round_order = [actor.player_id, target.player_id]

        with patch.object(engine, "_emit_vis") as emit_vis:
            engine._apply_character_start(state, actor)

        self.assertTrue(any(call.args[0] == "mark_resolved" for call in emit_vis.call_args_list))

    def test_manshin_mark_none_emits_visibility_event(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        actor = state.players[0]
        actor.current_character = "만신"
        state.current_round_order = [actor.player_id]

        with patch.object(engine, "_emit_vis") as emit_vis:
            engine._apply_character_start(state, actor)

        self.assertTrue(any(call.args[0] == "mark_target_none" for call in emit_vis.call_args_list))

    def test_swindler_takeover_multiplier_three_below_eight_shards(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        swindler = state.players[0]
        owner = state.players[1]
        pos = first_t3_position(state)
        swindler.current_character = "사기꾼"
        swindler.shards = 7
        swindler.cash = 20
        swindler.position = pos
        owner.current_character = "아전"
        owner.tiles_owned = 1
        state.tile_owner[pos] = owner.player_id
        base_rent = engine._effective_rent(state, pos, swindler, owner.player_id)
        result = engine._resolve_landing(state, swindler)
        self.assertEqual(result["type"], "SWINDLE_TAKEOVER")
        self.assertEqual(result.get("swindle_multiplier"), 3)
        self.assertEqual(swindler.cash, 20 - base_rent * 3)

    def test_swindler_takeover_multiplier_two_at_eight_shards(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        swindler = state.players[0]
        owner = state.players[1]
        pos = first_t3_position(state)
        swindler.current_character = "사기꾼"
        swindler.shards = 8
        swindler.cash = 20
        swindler.position = pos
        owner.current_character = "아전"
        owner.tiles_owned = 1
        state.tile_owner[pos] = owner.player_id
        base_rent = engine._effective_rent(state, pos, swindler, owner.player_id)
        result = engine._resolve_landing(state, swindler)
        self.assertEqual(result["type"], "SWINDLE_TAKEOVER")
        self.assertEqual(result.get("swindle_multiplier"), 2)
        self.assertEqual(swindler.cash, 20 - base_rent * 2)

    def test_result_summary_preserves_last_selected_character_for_dead_player(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        self._init_strategy_stats_for_mark_tests(engine)
        player = state.players[0]
        player.current_character = ""
        engine._strategy_stats[player.player_id]["last_selected_character"] = "중매꾼"
        result = engine._build_result(state)
        self.assertEqual(result.player_summary[0]["character"], "중매꾼")
        self.assertEqual(result.strategy_summary[0]["character"], "중매꾼")


class TrickRuleAuditTests(unittest.TestCase):
    def make_engine(self, policy=None, rng=None):
        return GameEngine(DEFAULT_CONFIG, policy or DummyPolicy(), rng=rng or random.Random(0), enable_logging=True)

    def make_state(self):
        return GameState.create(DEFAULT_CONFIG)

    def test_removed_anytime_rule_applies_to_all_trick_cards(self):
        deck = {card.name: card for card in build_trick_deck()}
        removed_anytime_cards = [
            "우대권",
            "무료 증정",
            "마당발",
            "뇌고왕",
            "뭘리권",
            "뭔칙휜",
            "강제 매각",
            "뇌절왕",
        ]
        for card_name in removed_anytime_cards:
            self.assertIn(card_name, deck)
            self.assertFalse(deck[card_name].is_anytime, msg=f"{card_name} should not be anytime")

    def test_pabal_ability1_adds_one_die_when_shards_below_eight(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=FixedRandom([1, 2, 3]), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = CARD_TO_NAMES[4][0]
        player.shards = 7

        engine._apply_character_start(state, player)
        move, movement = engine._resolve_move(state, player, MovementDecision(False, ()))

        self.assertEqual(move, 6)
        self.assertEqual(movement["mode"], "dice")
        self.assertEqual(len(movement["dice"]), 3)
        applied = next(
            row for row in reversed(engine._action_log)
            if row.get("event") == "character_ability_applied" and row.get("card_no") == 4
        )
        self.assertEqual(applied.get("ability_tier"), 1)
        self.assertEqual(applied.get("dice_mode"), "plus_one")

    def test_pabal_ability2_can_reduce_die_when_policy_selects_minus_one(self):
        engine = GameEngine(DEFAULT_CONFIG, PabalModePolicy("minus_one"), rng=FixedRandom([4]), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = CARD_TO_NAMES[4][0]
        player.shards = 8

        engine._apply_character_start(state, player)
        move, movement = engine._resolve_move(state, player, MovementDecision(False, ()))

        self.assertEqual(move, 4)
        self.assertEqual(movement["mode"], "dice")
        self.assertEqual(len(movement["dice"]), 1)
        applied = next(
            row for row in reversed(engine._action_log)
            if row.get("event") == "character_ability_applied" and row.get("card_no") == 4
        )
        self.assertEqual(applied.get("ability_tier"), 2)
        self.assertEqual(applied.get("dice_mode"), "minus_one")

    def test_pabal_below_eight_ignores_minus_one_request_and_stays_ability1(self):
        engine = GameEngine(DEFAULT_CONFIG, PabalModePolicy("minus_one"), rng=FixedRandom([2, 3, 4]), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = CARD_TO_NAMES[4][0]
        player.shards = 7

        engine._apply_character_start(state, player)
        move, movement = engine._resolve_move(state, player, MovementDecision(False, ()))

        self.assertEqual(move, 9)
        self.assertEqual(movement["mode"], "dice")
        self.assertEqual(len(movement["dice"]), 3)
        applied = next(
            row for row in reversed(engine._action_log)
            if row.get("event") == "character_ability_applied" and row.get("card_no") == 4
        )
        self.assertEqual(applied.get("ability_tier"), 1)
        self.assertEqual(applied.get("dice_mode"), "plus_one")

    def test_relic_collector_doubles_f_tile_shards(self):
        engine = self.make_engine()
        state = self.make_state()
        player = state.players[0]
        player.current_character = "객주"
        # 성물 수집가 효과를 적용한 상태를 직접 시뮬레이션한다.
        player.extra_shard_gain_this_turn = 1
        player.position = first_special_position(state, CellKind.F1)
        start_shards = player.shards

        event = engine._resolve_landing(state, player)

        self.assertEqual(event["type"], "F1")
        self.assertEqual(event["shards"], DEFAULT_CONFIG.rules.special_tiles.f1_shards * 2)
        self.assertEqual(player.shards - start_shards, DEFAULT_CONFIG.rules.special_tiles.f1_shards * 2)

    def test_relic_collector_does_not_modify_lap_reward_shards(self):
        class ShardPolicy(DummyPolicy):
            def choose_lap_reward(self, state, player):
                return LapRewardDecision("shards")

        engine = self.make_engine(policy=ShardPolicy())
        state = self.make_state()
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        player = state.players[0]
        player.extra_shard_gain_this_turn = 1
        start_shards = player.shards

        result = engine._apply_lap_reward(state, player)

        self.assertEqual(result["shards_delta"], DEFAULT_CONFIG.rules.lap_reward.shards)
        self.assertEqual(player.shards - start_shards, DEFAULT_CONFIG.rules.lap_reward.shards)

    def test_lap_reward_point_cost_defaults_follow_rule_document(self):
        rules = DEFAULT_CONFIG.rules.lap_reward
        self.assertEqual(rules.points_budget, 10)
        self.assertEqual(rules.cash_point_cost, 2)
        self.assertEqual(rules.shards_point_cost, 3)
        self.assertEqual(rules.coins_point_cost, 3)
        self.assertEqual(rules.cash_pool, 30)
        self.assertEqual(rules.shards_pool, 18)
        self.assertEqual(rules.coins_pool, 18)

    def test_selector_prompt_lap_reward_fixture_metadata_matches_gateway_choices(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.lap_reward_surface.json")
        metadata = fixture["metadata"]
        state = SimpleNamespace(
            config=DEFAULT_CONFIG,
            lap_reward_cash_pool_remaining=30,
            lap_reward_shards_pool_remaining=18,
            lap_reward_coins_pool_remaining=18,
        )

        generated_choices = _build_lap_reward_legal_choices((), {}, state, None)
        generated_choice_ids = [str(choice["choice_id"]) for choice in generated_choices]

        self.assertEqual(
            metadata["expected_choice_ids"],
            ["cash-2_shards-1_coins-1", "cash-5_shards-0_coins-0", "cash-2_shards-2_coins-0"],
        )
        for choice_id in metadata["expected_choice_ids"]:
            self.assertIn(choice_id, generated_choice_ids)

    def test_selector_prompt_burden_fixture_metadata_matches_gateway_context(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.burden_exchange_surface.json")
        metadata = fixture["metadata"]
        burden_cards = [
            SimpleNamespace(deck_index=91, name="무거운 짐", description="이동 -1", burden_cost=4, is_burden=True),
            SimpleNamespace(deck_index=92, name="가벼운 짐", description="효과 없음", burden_cost=2, is_burden=True),
            SimpleNamespace(deck_index=93, name="호객꾼", description="말 효과", burden_cost=2, is_burden=True),
        ]
        player = SimpleNamespace(trick_hand=list(burden_cards), hand_coins=0)
        state = SimpleNamespace(next_supply_f_threshold=6, f_value=3)

        context = _build_burden_exchange_context((None, None, burden_cards[0]), {}, state, player)

        self.assertEqual(metadata["expected_current_target_deck_index"], 91)
        self.assertEqual(context["card_deck_index"], metadata["expected_current_target_deck_index"])
        self.assertEqual(
            [str(item["name"]) for item in context["burden_cards"]],
            metadata["expected_card_names"],
        )

    def test_selector_prompt_coin_placement_fixture_metadata_matches_gateway_choices(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.coin_placement_surface.json")
        metadata = fixture["metadata"]
        player = SimpleNamespace(player_id=1, visited_owned_tile_indices=[12, 18, 24])
        state = SimpleNamespace(tile_owner=[None] * 40)
        state.tile_owner[12] = 1
        state.tile_owner[18] = 1
        state.tile_owner[24] = 1

        choices = _build_coin_placement_choices((), {}, state, player)

        self.assertEqual([choice["choice_id"] for choice in choices], metadata["expected_choice_ids"])
        self.assertEqual(len(choices), metadata["owned_tile_count"])

    def test_selector_prompt_geo_bonus_fixture_metadata_matches_gateway_choices(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.geo_bonus_surface.json")
        metadata = fixture["metadata"]

        choices = _build_geo_bonus_choices((), {}, None, None)

        self.assertEqual([choice["choice_id"] for choice in choices], metadata["expected_choice_ids"])

    def test_selector_prompt_movement_fixture_metadata_matches_gateway_choices(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.movement_surface.json")
        metadata = fixture["metadata"]
        player = SimpleNamespace(used_dice_cards={1, 3, 4, 6})

        choices = _build_movement_legal_choices((), {}, None, player)

        self.assertEqual([choice["choice_id"] for choice in choices], metadata["expected_choice_ids"])
        self.assertEqual(choices[0]["choice_id"], metadata["roll_choice_id"])

    def test_selector_prompt_runaway_fixture_metadata_matches_gateway_choices(self):
        fixture = _load_selector_prompt_fixture("selector.prompt.runaway_step_surface.json")
        metadata = fixture["metadata"]

        choices = _build_runaway_legal_choices((None, None, 17, 18, "운수"), {}, None, None)

        self.assertEqual([choice["choice_id"] for choice in choices], metadata["expected_choice_ids"])
        self.assertEqual(choices[0]["choice_id"], metadata["bonus_choice_id"])
        self.assertEqual(choices[1]["choice_id"], metadata["stay_choice_id"])

    def test_lap_reward_over_budget_request_is_trimmed_before_apply(self):
        class OverBudgetPolicy(DummyPolicy):
            def choose_lap_reward(self, state, player):
                # 1 cash + 3 coins => 11 points under 2/3/3 costs; must be trimmed to <= 10.
                return LapRewardDecision("coins", cash_units=1, shard_units=0, coin_units=3)

        engine = self.make_engine(policy=OverBudgetPolicy())
        state = self.make_state()
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(DEFAULT_CONFIG.player_count)
        ]
        player = state.players[0]
        start_cash = player.cash
        start_coins = player.hand_coins

        result = engine._apply_lap_reward(state, player)

        self.assertLessEqual(result["requested_points"], DEFAULT_CONFIG.rules.lap_reward.points_budget)
        self.assertLessEqual(result["granted_points"], DEFAULT_CONFIG.rules.lap_reward.points_budget)
        self.assertEqual(result["cash_delta"], 0)
        self.assertEqual(result["coins_delta"], 3)
        self.assertEqual(player.cash, start_cash)
        self.assertEqual(player.hand_coins, start_coins + 3)

    def test_trade_pass_waives_all_normal_rents_this_turn(self):
        engine = self.make_engine()
        state = self.make_state()
        player = state.players[0]
        owner = state.players[1]
        pos = first_t3_position(state)
        state.tile_owner[pos] = owner.player_id
        owner.tiles_owned = 1
        player.position = pos
        player.trick_all_rent_waiver_this_turn = True
        start_cash = player.cash

        first = engine._resolve_landing(state, player)
        second = engine._resolve_landing(state, player)

        self.assertEqual(first["type"], "RENT")
        self.assertEqual(second["type"], "RENT")
        self.assertEqual(first["rent"], 0)
        self.assertEqual(second["rent"], 0)
        self.assertEqual(player.cash, start_cash)
        self.assertTrue(player.trick_all_rent_waiver_this_turn)

    def test_trade_pass_does_not_zero_swindler_takeover_cost(self):
        engine = self.make_engine()
        state = self.make_state()
        swindler = state.players[0]
        owner = state.players[1]
        pos = first_t3_position(state)
        swindler.current_character = "사기꾼"
        swindler.cash = 20
        swindler.position = pos
        swindler.trick_all_rent_waiver_this_turn = True
        state.tile_owner[pos] = owner.player_id
        owner.tiles_owned = 1

        result = engine._resolve_landing(state, swindler)

        self.assertEqual(result["type"], "SWINDLE_TAKEOVER")
        self.assertLess(swindler.cash, 20)

    def test_force_sale_requires_preuse_flag(self):
        engine = self.make_engine()
        state = self.make_state()
        player = state.players[0]
        owner = state.players[1]
        pos = first_t3_position(state)
        player.position = pos
        state.tile_owner[pos] = owner.player_id
        owner.tiles_owned = 1

        plain_result = engine._resolve_landing(state, player)
        self.assertEqual(plain_result["type"], "RENT")

        player.position = pos
        player.cash = DEFAULT_CONFIG.economy.starting_cash
        player.trick_force_sale_landing_this_turn = True
        flagged_result = engine._resolve_landing(state, player)

        self.assertEqual(flagged_result["type"], "FORCE_SALE")
        self.assertIsNone(state.tile_owner[pos])

    def test_madangbal_expires_when_extra_purchase_fails(self):
        engine = self.make_engine()
        state = self.make_state()
        player = state.players[0]
        pos = first_t3_position(state)
        state.tile_owner[pos] = player.player_id
        player.tiles_owned = 1
        player.position = pos
        player.cash = 0
        player.trick_one_extra_adjacent_buy_this_turn = True

        engine._resolve_landing(state, player)

        self.assertFalse(player.trick_one_extra_adjacent_buy_this_turn)

    def test_zone_chain_uses_current_turn_rolled_dice_count(self):
        engine = self.make_engine(rng=FixedRandom((6,)))
        state = self.make_state()
        player = state.players[0]
        pos = first_t3_position(state)
        state.tile_owner[pos] = player.player_id
        player.tiles_owned = 1
        player.position = pos
        player.trick_zone_chain_this_turn = True
        player.rolled_dice_count_this_turn = 1

        result = engine._resolve_landing(state, player)

        self.assertEqual(result["type"], "ZONE_CHAIN")
        self.assertEqual(result["extra_move"], 6)
        self.assertEqual(result["movement"]["dice"], [6])

    def test_shineuiddeut_uses_actor_shards_for_same_tile_settlement(self):
        engine = self.make_engine()
        state = self.make_state()
        player = state.players[0]
        opponent = state.players[1]
        pos = first_t3_position(state)
        state.tile_owner[pos] = player.player_id
        player.tiles_owned = 1
        player.position = pos
        opponent.position = pos
        opponent.cash = 20
        player.shards = 2
        opponent.shards = 5
        player.trick_same_tile_shard_rake_this_turn = True

        event = engine._resolve_landing(state, player)

        self.assertEqual(event["trick_same_tile_shard_rake"]["details"][0]["amount"], 2)


if __name__ == "__main__":
    unittest.main()
