export const KNOWN_PROMPT_TYPES = [
  "movement",
  "runaway_step_choice",
  "lap_reward",
  "draft_card",
  "final_character",
  "trick_to_use",
  "purchase_tile",
  "hidden_trick_card",
  "mark_target",
  "coin_placement",
  "geo_bonus",
  "doctrine_relief",
  "active_flip",
  "specific_trick_reward",
  "burden_exchange",
] as const;

const PROMPT_TYPE_LABELS: Record<string, string> = {
  movement: "이동값 결정",
  runaway_step_choice: "탈출 노비 이동 선택",
  lap_reward: "랩 보상 선택",
  draft_card: "드래프트 선택",
  final_character: "최종 캐릭터 선택",
  final_character_choice: "최종 캐릭터 선택",
  trick_to_use: "잔꾀 사용",
  purchase_tile: "토지 구매",
  hidden_trick_card: "히든 잔꾀 지정",
  mark_target: "지목 대상 선택",
  coin_placement: "승점 배치",
  geo_bonus: "지리 보너스 선택",
  doctrine_relief: "교리 감독관 구제",
  active_flip: "액티브 카드 뒤집기",
  specific_trick_reward: "특정 잔꾀 보상",
  burden_exchange: "짐 교환",
};

export function promptLabelForType(requestType: string): string {
  if (!requestType.trim()) {
    return "선택 요청";
  }
  return PROMPT_TYPE_LABELS[requestType] ?? requestType;
}
