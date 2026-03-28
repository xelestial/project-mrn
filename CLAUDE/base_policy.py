"""base_policy.py — engine이 policy에 요청하는 결정 계약.

이 Protocol은 engine.py / effect_handlers.py가 실제로 호출하는
choose_* 메서드 전체를 명세한다.

용도:
- HumanDecisionAdapter, AIDecisionAdapter 구현 시 필수 메서드 목록
- 타입 체크: isinstance(policy, BasePolicy) — runtime_checkable
- engine.py 자체는 수정 불필요. Protocol은 강제 상속이 아닌 계약 명세다.

제외된 항목 (AI 전용 / 선택적):
- pop_debug          — 디버그 로그 전용, engine은 hasattr 후 호출
- character_mode_for_player — AI 전략 메타데이터
- lap_mode_for_player       — AI 전략 메타데이터
- _landing_score            — AI 전략 메타데이터
- set_rng                   — 재현성 설정, hasattr 후 호출
- register_policy_hook      — 훅 등록, hasattr 후 호출
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BasePolicy(Protocol):
    """Engine이 한 게임 세션 동안 policy에 요청하는 결정 계약.

    필수 메서드: engine/effect_handlers가 hasattr 없이 직접 호출하는 것들.
    선택적 메서드: engine이 getattr fallback과 함께 호출하는 것들.
    """

    # ------------------------------------------------------------------
    # 필수 — engine/effect_handlers가 직접 호출
    # ------------------------------------------------------------------

    def choose_movement(self, state: Any, player: Any) -> Any:
        """이동 방법 선택 (주사위 / 카드 조합)."""
        ...

    def choose_draft_card(self, state: Any, player: Any, offered_cards: Any) -> Any:
        """드래프트 카드 선택."""
        ...

    def choose_final_character(self, state: Any, player: Any, card_choices: Any) -> Any:
        """최종 캐릭터 선택."""
        ...

    def choose_lap_reward(self, state: Any, player: Any) -> Any:
        """출발점 통과 보상 선택 (현금 / 코인 / 조각)."""
        ...

    def choose_trick_to_use(self, state: Any, player: Any, hand: Any) -> Any:
        """사용할 트릭 카드 선택. 없으면 None 반환."""
        ...

    def choose_hidden_trick_card(self, state: Any, player: Any, hand: Any) -> Any:
        """숨길 트릭 카드 선택."""
        ...

    def choose_mark_target(self, state: Any, player: Any, actor_name: Any) -> Any:
        """표적 마킹 대상 선택."""
        ...

    def choose_coin_placement_tile(self, state: Any, player: Any) -> Any:
        """코인 배치 타일 선택."""
        ...

    def choose_geo_bonus(self, state: Any, player: Any, char: Any) -> Any:
        """지형 보너스 선택 (지리학자)."""
        ...

    def choose_doctrine_relief_target(self, state: Any, player: Any, candidates: Any) -> Any:
        """교리 구제 대상 선택."""
        ...

    def choose_active_flip_card(self, state: Any, player: Any, flippable_cards: Any) -> Any:
        """능동적 카드 뒤집기 선택. 없으면 None 반환."""
        ...

    def choose_specific_trick_reward(self, state: Any, player: Any, choices: Any) -> Any:
        """특정 트릭 보상 선택. 없으면 None 반환."""
        ...

    # ------------------------------------------------------------------
    # 선택적 — engine이 getattr fallback과 함께 호출
    #   구현하지 않으면 engine의 기본값이 사용된다.
    # ------------------------------------------------------------------

    def choose_purchase_tile(
        self,
        state: Any,
        player: Any,
        pos: Any,
        cell: Any,
        cost: Any,
        *,
        source: str = "landing",
    ) -> bool:
        """타일 구매 여부 결정. 기본값: True (구매)."""
        return True

    def choose_burden_exchange_on_supply(
        self, state: Any, player: Any, card: Any
    ) -> bool:
        """보급 시 부담 카드 교환 여부. 기본값: 현금이 충분하면 True."""
        return True
