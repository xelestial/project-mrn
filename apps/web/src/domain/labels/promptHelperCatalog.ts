export const DEFAULT_PROMPT_HELPER_TEXT = "현재 상황에서 진행할 선택지를 하나 고르세요.";

const PROMPT_HELPERS: Record<string, string> = {
  movement: "주사위를 굴리거나 주사위 카드를 사용해 이번 턴의 이동값을 결정하세요.",
  runaway_step_choice: "탈출 노비 효과를 적용해 안전칸/운수칸으로 이동할지 선택하세요.",
  lap_reward: "랩 보상(현금/조각/승점) 중 현재 상황에 맞는 보상을 선택하세요.",
  draft_card: "이번 턴에 사용할 인물을 클릭해서 선택하세요.",
  final_character: "드래프트한 인물 중 최종 캐릭터를 선택하세요.",
  final_character_choice: "드래프트한 인물 중 최종 캐릭터를 선택하세요.",
  trick_to_use: "지금 타이밍에 사용할 잔꾀를 선택하거나 사용하지 않음을 고르세요.",
  purchase_tile: "도착한 토지를 구매할지, 구매 없이 턴을 종료할지 선택하세요.",
  hidden_trick_card: "보유 잔꾀 중 이번 라운드 히든으로 지정할 카드를 선택하세요.",
  mark_target: "지목 효과를 적용할 대상(인물/플레이어)을 선택하세요.",
  coin_placement: "획득한 승점 토큰을 배치할 칸을 선택하세요.",
  geo_bonus: "객주 보너스 효과를 하나 선택하세요.",
  doctrine_relief: "교리 해제 효과를 적용할 대상을 선택하세요.",
  active_flip: "카드 한 장을 뒤집거나, 뒤집기를 종료하세요.",
  specific_trick_reward: "지정된 잔꾀 보상 카드를 선택하세요.",
  burden_exchange: "짐 카드를 교환할지 선택하세요.",
};

export function promptHelperForType(requestType: string): string {
  return PROMPT_HELPERS[requestType] ?? DEFAULT_PROMPT_HELPER_TEXT;
}
