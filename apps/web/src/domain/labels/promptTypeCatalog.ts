import type { LocaleMessages } from "../../i18n/types";
import { PROMPT_TYPE_TEXT } from "../text/uiText";

export const KNOWN_PROMPT_TYPES = [
  "movement",
  "runaway_step_choice",
  "lap_reward",
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
] as const;

type PromptTypeText = LocaleMessages["promptType"];

export function promptLabelForType(requestType: string, promptTypeText: PromptTypeText = PROMPT_TYPE_TEXT): string {
  if (!requestType.trim()) {
    return promptTypeText.generic;
  }
  return promptTypeText.labels[requestType as keyof typeof promptTypeText.labels] ?? requestType;
}
