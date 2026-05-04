"""Shared replay/live user-facing phrase dictionary."""
from __future__ import annotations

EVENT_LABELS_KO: dict[str, str] = {
    "session_start": "세션 시작",
    "round_start": "라운드 시작",
    "weather_reveal": "날씨 공개",
    "draft_pick": "드래프트 선택",
    "final_character_choice": "최종 캐릭터 선택",
    "turn_start": "턴 시작",
    "trick_used": "잔꾀 사용",
    "dice_roll": "이동값 결정",
    "player_move": "말 이동",
    "landing_resolved": "도착 칸 처리",
    "rent_paid": "렌트 지불",
    "tile_purchased": "토지 구매",
    "fortune_drawn": "운수 카드 공개",
    "fortune_resolved": "운수 효과 처리",
    "mark_resolved": "지목 처리",
    "mark_blocked": "지목 차단",
    "ability_suppressed": "능력 차단",
    "marker_transferred": "징표 이동",
    "marker_flip": "징표 카드 뒤집기",
    "lap_reward_chosen": "랩 보상 선택",
    "f_value_change": "종료 시간 변화",
    "bankruptcy": "파산",
    "turn_end_snapshot": "턴 종료",
    "game_end": "게임 종료",
}

LANDING_TYPE_LABELS_KO: dict[str, str] = {
    "PURCHASE": "토지 구매",
    "PURCHASE_FAIL": "토지 구매 실패",
    "PURCHASE_SKIP_POLICY": "구매 없이 턴 종료",
    "PURCHASE_BLOCKED_THIS_TURN": "토지 구매 불가",
    "RENT": "통행료 정산",
    "RENT_FAILSAFE": "통행료 정산",
    "FORTUNE": "운수 처리",
    "MARK": "지목 처리",
    "FORCE_SALE": "강제 매각",
    "NO_EFFECT": "효과 없음",
}
