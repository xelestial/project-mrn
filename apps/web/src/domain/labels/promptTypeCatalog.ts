import type { LocaleMessages } from "../../i18n/types";
import { DEFAULT_PROMPT_TYPE_TEXT } from "../../i18n/defaultText";

export const KNOWN_PROMPT_TYPES = [
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

type PromptTypeText = LocaleMessages["promptType"];

export function promptLabelForType(requestType: string, promptTypeText: PromptTypeText = DEFAULT_PROMPT_TYPE_TEXT): string {
  if (!requestType.trim()) {
    return promptTypeText.generic;
  }
  return promptTypeText.labels[requestType as keyof typeof promptTypeText.labels] ?? requestType;
}
