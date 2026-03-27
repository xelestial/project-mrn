from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ai_policy import ArenaPolicy, BasePolicy, HeuristicPolicy, LapRewardDecision, MovementDecision
from characters import CARD_TO_NAMES, CHARACTERS
from config import DEFAULT_CONFIG, CellKind
from engine import GameEngine, GameResult
from metadata import GAME_VERSION
from state import GameState, PlayerState
from text_encoding import configure_utf8_io
from trick_cards import TrickCard

CELL_LABELS = {
    CellKind.F1: "F1",
    CellKind.F2: "F2",
    CellKind.S: "S ",
    CellKind.T2: "T2",
    CellKind.T3: "T3",
    CellKind.MALICIOUS: "M ",
}

INTERESTING_EVENTS = {
    "initial_public_tricks",
    "initial_active_faces",
    "round_order",
    "turn",
    "mark_queued",
    "mark_blocked",
    "mark_target_missing",
    "mark_target_none",
    "assassin_reveal",
    "bandit_tax",
    "baksu_transfer",
    "baksu_transfer_none",
    "manshin_burden_clear",
    "forced_move",
    "marker_flip",
    "marker_flip_skip",
    "trick_supply",
    "fortune_reshuffle",
    "trick_reshuffle",
}


@dataclass
class DebugControls:
    reveal_all: bool = True
    step: bool = True
    show_board_every_step: bool = False
    show_last_action_json: bool = False


class DebugCLIInspector:
    def __init__(self, controls: DebugControls):
        self.controls = controls
        self.last_row: dict | None = None

    def on_event(self, engine: "CLIDebugGameEngine", row: dict) -> None:
        self.last_row = row
        event = row.get("event")
        if event not in INTERESTING_EVENTS:
            return
        self._print_event(row)
        if self.controls.show_last_action_json:
            print(json.dumps(row, ensure_ascii=False, indent=2))
        if self.controls.step:
            self._step_prompt(engine)

    def _print_event(self, row: dict) -> None:
        event = row.get("event")
        if event == "turn":
            landing = row.get("landing") or {}
            landing_type = landing.get("type", "-")
            extra = f" landing={landing_type}"
            if "cost" in landing:
                extra += f" cost={landing['cost']}"
            if "rent" in landing:
                extra += f" rent={landing['rent']}"
            if "skipped" in landing:
                extra += f" skipped={landing['skipped']}"
            print(
                f"\n[TURN] R{row['round_index']} G{row['turn_index_global']} P{row['player']}({row.get('character') or '-'}) "
                f"{row['start_pos']} -> {row['end_pos']} move={row['move']} cash {row['cash_before']}->{row['cash_after']}"
                f" tiles {row['tiles_before']}->{row['tiles_after']} F {row['f_before']}->{row['f_after']}{extra}"
            )
            return
        print(f"[{event}] {json.dumps(row, ensure_ascii=False)}")

    def _step_prompt(self, engine: "CLIDebugGameEngine") -> None:
        state = engine.state
        while True:
            cmd = input("[step] 엔터=계속 | h=도움 | b=보드 | p=플레이어 | a=마지막이벤트 | q=종료 > ").strip().lower()
            if cmd == "":
                if self.controls.show_board_every_step:
                    engine.render_state(title="step")
                return
            if cmd == "h":
                print("엔터 계속 / b 전체상태 / p 플레이어 상세 / a 마지막 이벤트 JSON / q 종료")
                continue
            if cmd == "b":
                engine.render_state(title="step board")
                continue
            if cmd.startswith("p"):
                suffix = cmd[1:].strip()
                if not suffix:
                    suffix = input("플레이어 번호(1-4)> ").strip()
                try:
                    engine.render_player_detail(int(suffix))
                except Exception as exc:
                    print(f"오류: {exc}")
                continue
            if cmd == "a":
                if self.last_row is None:
                    print("마지막 이벤트가 없습니다.")
                else:
                    print(json.dumps(self.last_row, ensure_ascii=False, indent=2))
                continue
            if cmd == "q":
                raise SystemExit(0)
            print("알 수 없는 명령입니다. h 를 보세요.")


class CLIDebugGameEngine(GameEngine):
    def __init__(self, *args, inspector: DebugCLIInspector | None = None, **kwargs):
        self.inspector = inspector
        super().__init__(*args, **kwargs)

    def _log(self, row: dict) -> None:
        super()._log(row)
        if self.inspector is not None:
            self.inspector.on_event(self, row)

    def render_state(self, title: str = "", focus_player_id: int | None = None) -> None:
        state = self.state
        focus = state.players[focus_player_id - 1] if focus_player_id else None
        print("\n" + "=" * 96)
        header = f"DEBUG BOARD {title}".strip()
        print(header)
        print(
            f"version={GAME_VERSION} turn_global={state.turn_index + 1} round={state.rounds_completed + 1} "
            f"F={state.f_value} marker=P{state.marker_owner_id + 1} active_by_card={state.active_by_card}"
        )
        print("-- 플레이어 --")
        for p in state.players:
            mark = "*" if focus and p.player_id == focus.player_id else " "
            print(
                f"{mark}P{p.player_id + 1} alive={p.alive} pos={p.position} char={p.current_character or '-'} cash={p.cash} "
                f"tiles={p.tiles_owned} blocks={len(p.block_ids_owned)} scorePlaced={p.score_coins_placed} handCoins={p.hand_coins} shards={p.shards} turns={p.turns_taken}"
            )
            print(
                f"   tricks(all)={[c.name for c in p.trick_hand]} public={p.public_trick_names()} "
                f"hidden_count={p.hidden_trick_count()} pending_marks={p.pending_marks} drafted={p.drafted_cards}"
            )
        print("-- 보드 --")
        for i, cell in enumerate(state.board):
            owner = state.tile_owner[i]
            occ = [f"P{p.player_id + 1}" for p in state.players if p.alive and p.position == i]
            owner_s = "-" if owner is None else f"P{owner + 1}"
            rule = ""
            if cell in (CellKind.T2, CellKind.T3):
                buy = state.config.economy.purchase_cost_for(state.board, i)
                rent = state.config.economy.rent_cost_for(state.board, i)
                rule = f" buy={buy} rent={rent} coin={state.tile_coins[i]} block={state.block_ids[i]}"
            elif cell == CellKind.MALICIOUS:
                rule = f" malicious={state.config.economy.malicious_cost_for(state.board, i, state.config.board.malicious_land_multiplier)}"
            print(f"[{i:02d}] {CELL_LABELS[cell]} owner={owner_s:<3} occ={','.join(occ) or '-':<8}{rule}")
        print("=" * 96)

    def render_player_detail(self, seat_1_based: int) -> None:
        if seat_1_based < 1 or seat_1_based > len(self.state.players):
            raise ValueError("플레이어 번호는 1~4")
        p = self.state.players[seat_1_based - 1]
        print("\n" + "-" * 72)
        print(f"P{seat_1_based} detail")
        print(json.dumps({
            "player_id": p.player_id + 1,
            "alive": p.alive,
            "position": p.position,
            "current_character": p.current_character,
            "cash": p.cash,
            "tiles_owned": p.tiles_owned,
            "block_ids_owned": sorted(p.block_ids_owned),
            "score_coins_placed": p.score_coins_placed,
            "hand_coins": p.hand_coins,
            "shards": p.shards,
            "drafted_cards": p.drafted_cards,
            "trick_hand": [c.name for c in p.trick_hand],
            "public_tricks": p.public_trick_names(),
            "hidden_trick_count": p.hidden_trick_count(),
            "pending_marks": p.pending_marks,
            "used_dice_cards": p.used_dice_cards,
            "laps_completed": p.laps_completed,
            "lap_rewards_received": p.lap_rewards_received,
            "turns_taken": p.turns_taken,
        }, ensure_ascii=False, indent=2))
        print("-" * 72)


class HumanPolicy(BasePolicy):
    def __init__(self, human_players: set[int], ai_mode: str = "arena", rng: random.Random | None = None, engine: CLIDebugGameEngine | None = None):
        self.human_players = set(human_players)
        self.rng = rng or random.Random()
        self.engine = engine
        if ai_mode == "arena":
            self.ai_policy = ArenaPolicy(rng=self.rng)
            self._ai_mode = "arena"
        else:
            self.ai_policy = HeuristicPolicy(character_policy_mode=ai_mode, lap_policy_mode="heuristic_v1", rng=self.rng)
            self._ai_mode = ai_mode

    def set_engine(self, engine: CLIDebugGameEngine) -> None:
        self.engine = engine

    def set_rng(self, rng) -> None:
        self.rng = rng
        if hasattr(self.ai_policy, "set_rng"):
            self.ai_policy.set_rng(rng)

    def character_mode_for_player(self, player_id: int) -> str:
        if player_id + 1 in self.human_players:
            return "human_debug"
        if hasattr(self.ai_policy, "character_mode_for_player"):
            return self.ai_policy.character_mode_for_player(player_id)
        return self._ai_mode

    def pop_debug(self, action: str, player_id: int):
        if player_id + 1 in self.human_players:
            return None
        if hasattr(self.ai_policy, "pop_debug"):
            return self.ai_policy.pop_debug(action, player_id)
        return None

    def _is_human(self, player: PlayerState) -> bool:
        return player.player_id + 1 in self.human_players

    def _delegate(self, method_name: str, *args, **kwargs):
        return getattr(self.ai_policy, method_name)(*args, **kwargs)

    def _render_state(self, state: GameState, focus: Optional[PlayerState] = None, title: str = "") -> None:
        if self.engine is not None:
            self.engine.render_state(title=title, focus_player_id=(focus.player_id + 1) if focus else None)

    def _input(self, prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError:
            print()
            raise SystemExit(0)

    def _ask_choice(self, prompt: str, valid: dict[str, object], allow_blank: bool = False):
        while True:
            raw = self._input(prompt).strip()
            if raw == "" and allow_blank:
                return None
            if raw == ":board":
                if self.engine is not None:
                    self.engine.render_state(title="manual board")
                continue
            if raw.startswith(":p"):
                if self.engine is not None:
                    suffix = raw[2:].strip() or self._input("플레이어 번호(1-4)> ").strip()
                    self.engine.render_player_detail(int(suffix))
                continue
            if raw == ":last":
                if self.engine is not None and self.engine.inspector and self.engine.inspector.last_row:
                    print(json.dumps(self.engine.inspector.last_row, ensure_ascii=False, indent=2))
                continue
            if raw in valid:
                return valid[raw]
            print(f"잘못된 입력입니다. 가능한 값: {', '.join(valid.keys())}. 추가 명령 :board, :pN, :last")

    def _yes_no(self, prompt: str, default: bool = True) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            raw = self._input(f"{prompt} {suffix} ").strip().lower()
            if raw in {":board", ":b"}:
                if self.engine is not None:
                    self.engine.render_state(title="manual board")
                continue
            if raw == ":last":
                if self.engine is not None and self.engine.inspector and self.engine.inspector.last_row:
                    print(json.dumps(self.engine.inspector.last_row, ensure_ascii=False, indent=2))
                continue
            if not raw:
                return default
            if raw in {"y", "yes", "1"}:
                return True
            if raw in {"n", "no", "0"}:
                return False
            print("y 또는 n 으로 입력하세요. 추가 명령 :board, :last")

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        if not self._is_human(player):
            return self._delegate("choose_hidden_trick_card", state, player, hand)
        self._render_state(state, player, "숨길 잔꾀 1장 선택")
        for i, card in enumerate(hand, 1):
            print(f"{i}. {card.name} :: {card.description}")
        valid = {str(i): card for i, card in enumerate(hand, 1)}
        return self._ask_choice("숨길 카드 번호> ", valid)

    def choose_trick_to_use(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        if not self._is_human(player):
            return self._delegate("choose_trick_to_use", state, player, hand)
        self._render_state(state, player, "사용할 잔꾀 선택 (엔터=없음)")
        for i, card in enumerate(hand, 1):
            tag = "언제나" if card.is_anytime else "일반"
            print(f"{i}. [{tag}] {card.name} :: {card.description}")
        valid = {str(i): card for i, card in enumerate(hand, 1)}
        return self._ask_choice("사용할 카드 번호(엔터=없음)> ", valid, allow_blank=True)

    def choose_specific_trick_reward(self, state: GameState, player: PlayerState, choices: list[TrickCard]) -> TrickCard | None:
        if not self._is_human(player):
            return self._delegate("choose_specific_trick_reward", state, player, choices)
        self._render_state(state, player, "특정 보상 잔꾀 선택")
        for i, card in enumerate(choices, 1):
            print(f"{i}. {card.name} :: {card.description}")
        valid = {str(i): card for i, card in enumerate(choices, 1)}
        return self._ask_choice("보상 카드 번호> ", valid)

    def choose_burden_exchange_on_supply(self, state: GameState, player: PlayerState, card: TrickCard) -> bool:
        if not self._is_human(player):
            return self._delegate("choose_burden_exchange_on_supply", state, player, card)
        self._render_state(state, player, f"보급: 짐 교체 여부 ({card.name}, 비용={card.burden_cost})")
        return self._yes_no(f"{card.name}를 {card.burden_cost}냥 내고 교환할까요?", default=True)

    def choose_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, cost: int, *, source: str = "landing") -> bool:
        if not self._is_human(player):
            return self._delegate("choose_purchase_tile", state, player, pos, cell, cost, source=source)
        self._render_state(state, player, f"토지 구매 여부 ({source})")
        print(f"칸={pos} cell={cell.name} cost={cost} current_cash={player.cash}")
        return self._yes_no("구매할까요?", default=True)

    def choose_movement(self, state: GameState, player: PlayerState) -> MovementDecision:
        if not self._is_human(player):
            return self._delegate("choose_movement", state, player)
        self._render_state(state, player, "이동 선택")
        remaining = [v for v in state.config.dice_cards.values if v not in player.used_dice_cards]
        print(f"남은 주사위 카드={remaining}")
        print("0. 일반 주사위 굴리기")
        if remaining:
            print("1. 카드 1장 사용")
        if len(remaining) >= 2:
            print("2. 카드 2장 사용")
        mode = self._input("선택> ").strip() or "0"
        if mode == "0":
            return MovementDecision(use_cards=False)
        if mode == "1" and remaining:
            valid = {str(v): v for v in remaining}
            value = self._ask_choice(f"사용할 카드 값 {remaining}> ", valid)
            return MovementDecision(use_cards=True, card_values=(value,))
        if mode == "2" and len(remaining) >= 2:
            first = self._ask_choice(f"첫 카드 값 {remaining}> ", {str(v): v for v in remaining})
            rem2 = [v for v in remaining if v != first]
            second = self._ask_choice(f"둘째 카드 값 {rem2}> ", {str(v): v for v in rem2})
            return MovementDecision(use_cards=True, card_values=(first, second))
        print("잘못된 선택이어서 일반 주사위로 처리합니다.")
        return MovementDecision(use_cards=False)

    def choose_lap_reward(self, state: GameState, player: PlayerState) -> LapRewardDecision:
        if not self._is_human(player):
            return self._delegate("choose_lap_reward", state, player)
        self._render_state(state, player, "랩 보상 선택")
        valid = {"1": "cash", "2": "shards", "3": "coins", "cash": "cash", "shards": "shards", "coins": "coins"}
        value = self._ask_choice(
            f"1.cash(+{state.config.coins.lap_reward_cash}) 2.shards(+{state.config.shards.lap_reward_shards}) 3.coins(+{state.config.coins.lap_reward_coins}) > ",
            valid,
        )
        return LapRewardDecision(choice=value)

    def choose_coin_placement_tile(self, state: GameState, player: PlayerState) -> Optional[int]:
        if not self._is_human(player):
            return self._delegate("choose_coin_placement_tile", state, player)
        candidates = [i for i, owner in enumerate(state.tile_owner) if owner == player.player_id and state.tile_coins[i] < state.config.coins.max_coins_per_tile]
        if not candidates:
            return None
        self._render_state(state, player, "승점 코인 배치 칸 선택")
        for idx in candidates:
            print(f"{idx}. coin={state.tile_coins[idx]} block={state.block_ids[idx]} cell={state.board[idx].name}")
        valid = {str(idx): idx for idx in candidates}
        return self._ask_choice("배치할 칸 번호(엔터=없음)> ", valid, allow_blank=True)

    def choose_draft_card(self, state: GameState, player: PlayerState, offered_cards: list[int]) -> int:
        if not self._is_human(player):
            return self._delegate("choose_draft_card", state, player, offered_cards)
        self._render_state(state, player, "드래프트 카드 선택")
        for i, card_no in enumerate(offered_cards, 1):
            names = CARD_TO_NAMES[card_no]
            active = state.active_by_card.get(card_no)
            print(f"{i}. card {card_no}: {names[0]} / {names[1]} (active={active})")
        valid = {str(i): offered_cards[i - 1] for i in range(1, len(offered_cards) + 1)}
        return self._ask_choice("카드 번호> ", valid)

    def choose_final_character(self, state: GameState, player: PlayerState, card_choices: list[int]) -> str:
        if not self._is_human(player):
            return self._delegate("choose_final_character", state, player, card_choices)
        self._render_state(state, player, "최종 인물 선택")
        options: dict[str, str] = {}
        idx = 1
        for card_no in card_choices:
            for name in CARD_TO_NAMES[card_no]:
                options[str(idx)] = name
                print(f"{idx}. {name} (card {card_no}, pair={CHARACTERS[name].pair}, active={state.active_by_card.get(card_no)})")
                idx += 1
        return self._ask_choice("인물 번호> ", options)

    def choose_mark_target(self, state: GameState, player: PlayerState, actor_name: str) -> Optional[str]:
        if not self._is_human(player):
            return self._delegate("choose_mark_target", state, player, actor_name)
        self._render_state(state, player, f"지목 대상 선택 ({actor_name})")
        try:
            source_idx = state.current_round_order.index(player.player_id)
            future_ids = set(state.current_round_order[source_idx + 1 :])
        except ValueError:
            future_ids = set()
        options = {"0": None}
        print("0. 지목 안 함")
        idx = 1
        for p in state.players:
            if p.alive and p.player_id in future_ids:
                options[str(idx)] = p.current_character
                print(f"{idx}. P{p.player_id + 1} {p.current_character} cash={p.cash} pos={p.position} tricks={[c.name for c in p.trick_hand]}")
                idx += 1
        return self._ask_choice("지목 번호> ", options)

    def choose_geo_bonus(self, state: GameState, player: PlayerState, actor_name: str) -> str:
        if not self._is_human(player):
            return self._delegate("choose_geo_bonus", state, player, actor_name)
        self._render_state(state, player, "객주 추가 보상 선택")
        valid = {"1": "cash", "2": "shards", "3": "coins", "cash": "cash", "shards": "shards", "coins": "coins"}
        return self._ask_choice("1.cash 2.shards 3.coins > ", valid)

    def choose_active_flip_card(self, state: GameState, player: PlayerState, flippable_cards: list[int]) -> Optional[int]:
        if not self._is_human(player):
            return self._delegate("choose_active_flip_card", state, player, flippable_cards)
        self._render_state(state, player, "징표 뒤집기 카드 선택")
        print("0. 안 뒤집음")
        options = {"0": None}
        for card_no in flippable_cards:
            names = CARD_TO_NAMES[card_no]
            print(f"{card_no}. {names[0]} / {names[1]} (active={state.active_by_card.get(card_no)})")
            options[str(card_no)] = card_no
        return self._ask_choice("카드 번호> ", options)


def parse_human_players(raw: str) -> set[int]:
    players: set[int] = set()
    for token in raw.split(','):
        token = token.strip()
        if not token:
            continue
        num = int(token)
        if num < 1 or num > 4:
            raise ValueError("human player ids must be between 1 and 4")
        players.add(num)
    return players or {1}


def run_cli(seed: int, humans: set[int], ai_mode: str, output_log: str | None = None, *, step: bool = True, show_board_every_step: bool = False, show_last_action_json: bool = False) -> GameResult:
    rng = random.Random(seed)
    inspector = DebugCLIInspector(DebugControls(step=step, show_board_every_step=show_board_every_step, show_last_action_json=show_last_action_json))
    policy = HumanPolicy(human_players=humans, ai_mode=ai_mode, rng=rng)
    engine = CLIDebugGameEngine(config=DEFAULT_CONFIG, policy=policy, rng=rng, enable_logging=True, inspector=inspector)
    policy.set_engine(engine)
    print(f"engine_version={GAME_VERSION} seed={seed} humans={sorted(humans)} ai_mode={ai_mode} step={step}")
    engine.render_state(title="initial")
    result = engine.run()
    print("\n=== 게임 종료 ===")
    print(json.dumps({
        "winner_ids": [w + 1 for w in result.winner_ids],
        "end_reason": result.end_reason,
        "total_turns": result.total_turns,
        "rounds_completed": result.rounds_completed,
        "alive_count": result.alive_count,
        "bankrupt_players": result.bankrupt_players,
        "final_f_value": result.final_f_value,
        "player_summary": result.player_summary,
    }, ensure_ascii=False, indent=2))
    if output_log:
        Path(output_log).write_text(json.dumps(result.action_log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"action_log saved to {output_log}")
    return result


def main() -> None:
    configure_utf8_io()
    parser = argparse.ArgumentParser(
        description="Engine-direct debug CLI. Uses the real engine/rules, lets selected seats act as humans, and reveals all information for full-game review."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--humans", type=str, default="1", help="Comma-separated 1-based player ids to control, e.g. 1 or 1,3")
    parser.add_argument("--ai-mode", type=str, default="arena", help="arena or heuristic policy name for non-human players")
    parser.add_argument("--output-log", type=str, default="")
    parser.add_argument("--no-step", action="store_true", help="Do not pause after every interesting engine event")
    parser.add_argument("--show-board-every-step", action="store_true", help="Render full board automatically at every step pause")
    parser.add_argument("--show-last-action-json", action="store_true", help="Print raw JSON for each interesting engine event")
    args = parser.parse_args()
    humans = parse_human_players(args.humans)
    run_cli(
        seed=args.seed,
        humans=humans,
        ai_mode=args.ai_mode,
        output_log=args.output_log or None,
        step=not args.no_step,
        show_board_every_step=args.show_board_every_step,
        show_last_action_json=args.show_last_action_json,
    )


if __name__ == "__main__":
    main()
