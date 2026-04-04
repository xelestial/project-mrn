const EVENT_LABELS: Record<string, string> = {
  session_created: "세션 생성",
  session_start: "세션 시작",
  session_started: "세션 시작됨",
  parameter_manifest: "설정 정보 동기화",
  seat_joined: "좌석 참가",
  round_start: "라운드 시작",
  weather_reveal: "날씨 공개",
  draft_pick: "드래프트 선택",
  final_character_choice: "최종 캐릭터 선택",
  turn_start: "턴 시작",
  dice_roll: "이동값 결정",
  trick_used: "잔꾀 사용",
  player_move: "말 이동",
  landing_resolved: "도착 칸 처리",
  rent_paid: "렌트 지불",
  tile_purchased: "토지 구매",
  marker_transferred: "징표 이동",
  marker_flip: "카드 뒤집기",
  lap_reward_chosen: "랩 보상 선택",
  fortune_drawn: "운수 공개",
  fortune_resolved: "운수 처리",
  turn_end_snapshot: "턴 종료",
  decision_requested: "선택 요청 등록",
  decision_resolved: "선택 처리 완료",
  decision_timeout_fallback: "시간 초과 자동 처리",
  bankruptcy: "파산",
  game_end: "게임 종료",
};

const NON_EVENT_LABELS: Record<string, string> = {
  prompt: "선택 요청",
  decision_ack: "선택 응답",
  heartbeat: "연결 상태",
  error: "오류",
};

export function eventLabelForCode(eventCode: string): string {
  if (!eventCode.trim()) {
    return "이벤트";
  }
  return EVENT_LABELS[eventCode] ?? eventCode;
}

export function nonEventLabelForMessageType(messageType: string): string {
  return NON_EVENT_LABELS[messageType] ?? "메시지";
}
