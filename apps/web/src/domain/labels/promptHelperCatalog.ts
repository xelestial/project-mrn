export const DEFAULT_PROMPT_HELPER_TEXT =
  "현재 가능한 선택지 중 하나를 선택하세요. 선택 즉시 엔진으로 전달됩니다.";

const PROMPT_HELPERS: Record<string, string> = {
  movement: "주사위를 굴리거나 주사위 카드를 사용해 이번 턴 이동값을 결정하세요.",
  runaway_step_choice: "한 칸이 모자랄 때 안전 칸 이동 또는 보너스 칸 이동을 선택하세요.",
  lap_reward: "랩 보상(현금/조각/승점) 중 원하는 보상을 선택하세요.",
  draft_card: "제시된 인물 중 이번 턴에 사용할 인물을 선택하세요.",
  final_character: "이번 라운드의 최종 캐릭터를 선택하세요.",
  final_character_choice: "이번 라운드의 최종 캐릭터를 선택하세요.",
  trick_to_use: "지금 타이밍에 사용할 잔꾀를 선택하거나 사용 안 함을 고르세요.",
  purchase_tile: "도착한 칸의 토지를 구매할지, 구매 없이 턴 종료할지 선택하세요.",
  hidden_trick_card: "이번 라운드 히든으로 지정할 잔꾀를 선택하세요.",
  mark_target: "지목 효과를 적용할 대상(인물/플레이어)을 선택하세요.",
  coin_placement: "이번 턴 승점을 배치할 타일을 선택하세요.",
  geo_bonus: "지리 보너스 대상 중 하나를 선택하세요.",
  doctrine_relief: "교리 감독관 구제 효과의 대상을 선택하세요.",
  active_flip: "이번 라운드 시작 전, 원하는 인물 카드를 뒤집으세요.",
  specific_trick_reward: "보상으로 받을 잔꾀 카드를 선택하세요.",
  burden_exchange: "교환할 짐 카드를 선택하세요.",
};

export function promptHelperForType(requestType: string): string {
  return PROMPT_HELPERS[requestType] ?? DEFAULT_PROMPT_HELPER_TEXT;
}
