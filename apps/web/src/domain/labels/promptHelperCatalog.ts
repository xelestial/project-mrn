export const DEFAULT_PROMPT_HELPER_TEXT = "현재 단계에서 필요한 선택입니다. 선택지를 확인하고 하나를 고르세요.";

const PROMPT_HELPERS: Record<string, string> = {
  movement: "주사위를 굴리거나 주사위 카드를 사용해 이번 턴 이동값을 결정하세요.",
  runaway_step_choice: "탈출 노비 이동 방식(기본 이동 / +1 추가 이동)을 선택하세요.",
  lap_reward: "랩 보상(현금/조각/승점) 중 하나를 선택하세요.",
  draft_card: "이번 턴에 사용할 인물 후보를 고르세요.",
  final_character: "최종 인물을 확정하세요.",
  final_character_choice: "최종 캐릭터를 확정하세요.",
  trick_to_use: "사용할 잔꾀를 선택하거나 이번에는 사용하지 않음을 고르세요.",
  purchase_tile: "도착한 칸의 토지를 구매할지, 구매 없이 턴을 마칠지 선택하세요.",
  hidden_trick_card: "보유한 잔꾀 중 이번 라운드 히든으로 지정할 카드를 선택하세요.",
  mark_target: "지목 효과를 적용할 대상(인물/플레이어)을 선택하세요.",
  coin_placement: "승점 토큰을 배치할 타일을 선택하세요.",
  geo_bonus: "지형 보너스를 적용할 대상을 선택하세요.",
  doctrine_relief: "교리 연구관 효과로 짐을 제거할 대상을 선택하세요.",
  active_flip: "뒤집을 카드를 한 장씩 선택하세요. 종료를 선택하면 카드 뒤집기를 마칩니다.",
  specific_trick_reward: "보상으로 받을 잔꾀를 선택하세요.",
  burden_exchange: "짐 카드 교환/제거 여부를 선택하세요.",
};

export function promptHelperForType(requestType: string): string {
  return PROMPT_HELPERS[requestType] ?? DEFAULT_PROMPT_HELPER_TEXT;
}
