import type { LocaleMessages } from "../../i18n/types";
import { PROMPT_HELPER_TEXT } from "../text/uiText";

type PromptHelperText = LocaleMessages["promptHelper"];

export const DEFAULT_PROMPT_HELPER_TEXT = PROMPT_HELPER_TEXT.default;

export function promptHelperForType(
  requestType: string,
  promptHelperText: PromptHelperText = PROMPT_HELPER_TEXT
): string {
  return promptHelperText.byType[requestType as keyof typeof promptHelperText.byType] ?? promptHelperText.default;
}
