export const SPECIALIZED_PROMPT_TYPES = [
  "movement",
  "runaway_step_choice",
  "lap_reward",
  "start_reward",
  "draft_card",
  "final_character",
  "final_character_choice",
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
  "trick_tile_target",
  "pabal_dice_mode",
] as const;

export function isSpecializedPromptType(requestType: string): boolean {
  return (SPECIALIZED_PROMPT_TYPES as readonly string[]).includes(requestType);
}
