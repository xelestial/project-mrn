import type { LocaleMessages } from "../../i18n/types";
import { DEFAULT_PROMPT_HELPER_TEXT as DEFAULT_HELPER_TEXT } from "../../i18n/defaultText";

type PromptHelperText = LocaleMessages["promptHelper"];

export const DEFAULT_PROMPT_HELPER_TEXT = DEFAULT_HELPER_TEXT.default;

export function promptHelperForType(
  requestType: string,
  promptHelperText: PromptHelperText = DEFAULT_HELPER_TEXT
): string {
  return promptHelperText.byType[requestType as keyof typeof promptHelperText.byType] ?? promptHelperText.default;
}
