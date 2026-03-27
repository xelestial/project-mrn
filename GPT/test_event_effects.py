import unittest

from config import DEFAULT_CONFIG, CellKind
from engine import GameEngine
from ai_policy import BasePolicy, MovementDecision, LapRewardDecision
from state import GameState


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
        return state.active_by_card[card_choices[0]]

    def choose_mark_target(self, state, player, actor_name):
        return None

    def choose_geo_bonus(self, state, player, actor_name):
        return "cash"


class EventEffectIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), enable_logging=False)
        self.state = GameState.create(DEFAULT_CONFIG)
        self.player = self.state.players[0]

    def test_event_dispatcher_registers_default_effect_events(self):
        names = self.engine.events.registered_event_names()
        self.assertIn('tile.purchase.attempt', names)
        self.assertIn('rent.payment.resolve', names)
        self.assertIn('fortune.draw.resolve', names)
        self.assertIn('fortune.cleanup.resolve', names)
        self.assertIn('fortune.card.apply', names)
        self.assertIn('fortune.movement.resolve', names)
        self.assertIn('game.end.evaluate', names)
        self.assertIn('weather.round.apply', names)
        self.assertIn('tile.character.effect', names)
        self.assertIn('landing.f.resolve', names)
        self.assertIn('landing.s.resolve', names)
        self.assertIn('landing.malicious.resolve', names)
        self.assertIn('landing.unowned.resolve', names)
        self.assertIn('landing.own_tile.resolve', names)
        self.assertIn('marker.management.apply', names)
        self.assertIn('marker.flip.resolve', names)
        self.assertIn('lap.reward.resolve', names)
        self.assertIn('payment.resolve', names)
        self.assertIn('bankruptcy.resolve', names)
        self.assertIn('trick.card.resolve', names)

    def test_purchase_can_be_overridden_by_custom_event_handler(self):
        land_pos = next(i for i, cell in enumerate(self.state.board) if cell in (CellKind.T2, CellKind.T3))
        cell = self.state.board[land_pos]
        self.engine.events.clear('tile.purchase.attempt')
        self.engine.events.register('tile.purchase.attempt', lambda state, player, pos, cell: {'type': 'CUSTOM_PURCHASE', 'pos': pos})
        result = self.engine._try_purchase_tile(self.state, self.player, land_pos, cell)
        self.assertEqual(result['type'], 'CUSTOM_PURCHASE')
        self.assertEqual(result['pos'], land_pos)

    def test_default_purchase_handler_still_buys_tile(self):
        land_pos = next(i for i, cell in enumerate(self.state.board) if cell in (CellKind.T2, CellKind.T3))
        cell = self.state.board[land_pos]
        result = self.engine._try_purchase_tile(self.state, self.player, land_pos, cell)
        self.assertEqual(result['type'], 'PURCHASE')
        self.assertEqual(self.state.tile_owner[land_pos], self.player.player_id)


    def test_unowned_landing_can_be_overridden(self):
        land_pos = next(i for i, cell in enumerate(self.state.board) if cell in (CellKind.T2, CellKind.T3) and self.state.tile_owner[i] is None)
        cell = self.state.board[land_pos]
        self.engine.events.clear('landing.unowned.resolve')
        self.engine.events.register('landing.unowned.resolve', lambda state, player, pos, cell: {'type': 'CUSTOM_UNOWNED', 'pos': pos})
        self.player.position = land_pos
        result = self.engine._resolve_landing(self.state, self.player)
        self.assertEqual(result['type'], 'CUSTOM_UNOWNED')
        self.assertEqual(result['pos'], land_pos)

    def test_own_tile_landing_can_be_overridden(self):
        land_pos = next(i for i, cell in enumerate(self.state.board) if cell in (CellKind.T2, CellKind.T3))
        self.state.tile_owner[land_pos] = self.player.player_id
        self.player.position = land_pos
        self.engine.events.clear('landing.own_tile.resolve')
        self.engine.events.register('landing.own_tile.resolve', lambda state, player, pos, cell: {'type': 'CUSTOM_OWN_TILE', 'pos': pos})
        result = self.engine._resolve_landing(self.state, self.player)
        self.assertEqual(result['type'], 'CUSTOM_OWN_TILE')
        self.assertEqual(result['pos'], land_pos)

    def test_default_f_landing_handler_applies_f_and_shards(self):
        f1_pos = next(i for i, cell in enumerate(self.state.board) if cell == CellKind.F1)
        self.player.position = f1_pos
        before_f = self.state.f_value
        before_shards = self.player.shards
        result = self.engine._resolve_landing(self.state, self.player)
        self.assertEqual(result['type'], 'F1')
        self.assertGreater(self.state.f_value, before_f)
        self.assertGreater(self.player.shards, before_shards)


    def test_lap_reward_can_be_overridden(self):
        self.engine.events.clear('lap.reward.resolve')
        self.engine.events.register('lap.reward.resolve', lambda state, player: {'choice': 'custom', 'coins_delta': 99})
        result = self.engine._apply_lap_reward(self.state, self.player)
        self.assertEqual(result['choice'], 'custom')

    def test_payment_can_be_overridden(self):
        self.engine.events.clear('payment.resolve')
        self.engine.events.register('payment.resolve', lambda state, player, cost, receiver: {'cost': cost, 'paid': True, 'bankrupt': False, 'custom': True})
        result = self.engine._pay_or_bankrupt(self.state, self.player, 3, None)
        self.assertTrue(result['custom'])



    def test_semantic_purchase_event_is_logged(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        land_pos = next(i for i, cell in enumerate(state.board) if cell in (CellKind.T2, CellKind.T3))
        cell = state.board[land_pos]
        engine._try_purchase_tile(state, player, land_pos, cell)
        semantic_rows = [row for row in engine._action_log if row.get('event') == 'tile.purchase.attempt']
        self.assertTrue(semantic_rows)
        row = semantic_rows[-1]
        self.assertEqual(row['event_kind'], 'semantic_event')
        self.assertTrue(row['returned_non_none'])
        self.assertEqual(row['args'][1]['player'], 1)

    def test_semantic_end_event_is_logged(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        engine._check_end(state)
        semantic_rows = [row for row in engine._action_log if row.get('event') == 'game.end.evaluate']
        self.assertTrue(semantic_rows)
        row = semantic_rows[-1]
        self.assertEqual(row['event_kind'], 'semantic_event')
        self.assertIn('results', row)

    def test_trick_card_can_be_overridden(self):
        from trick_cards import TrickCard
        card = TrickCard(deck_index=999, name='무료 증정', description='test')
        self.engine.events.clear('trick.card.resolve')
        self.engine.events.register('trick.card.resolve', lambda state, player, card: {'type': 'CUSTOM_TRICK', 'name': card.name})
        result = self.engine._apply_trick_card(self.state, self.player, card)
        self.assertEqual(result['type'], 'CUSTOM_TRICK')


    def test_fortune_card_apply_can_be_overridden(self):
        from fortune_cards import FortuneCard
        card = FortuneCard(deck_index=1, name='성과금', effect='x')
        self.engine.events.clear('fortune.card.apply')
        self.engine.events.register('fortune.card.apply', lambda state, player, card: {'type': 'CUSTOM_FORTUNE', 'name': card.name})
        result = self.engine._apply_fortune_card(self.state, self.player, card)
        self.assertEqual(result['type'], 'CUSTOM_FORTUNE')

    def test_fortune_movement_can_be_overridden(self):
        self.engine.events.clear('fortune.movement.resolve')
        self.engine.events.register('fortune.movement.resolve', lambda state, player, target_pos, trigger, card_name, movement_type: {'type': 'CUSTOM_MOVE', 'movement_type': movement_type, 'end_pos': target_pos})
        result = self.engine._apply_fortune_arrival(self.state, self.player, 3, 'test', '테스트')
        self.assertEqual(result['type'], 'CUSTOM_MOVE')
        self.assertEqual(result['movement_type'], 'arrival')

    def test_game_end_evaluate_can_be_overridden(self):
        self.engine.events.clear('game.end.evaluate')
        self.engine.events.register('game.end.evaluate', lambda state: True)
        result = self.engine._check_end(self.state)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
