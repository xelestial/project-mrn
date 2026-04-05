import { enLocale } from "./locales/en";
import { koLocale } from "./locales/ko";
import type { LocaleCode } from "./types";

export const DEFAULT_LOCALE: LocaleCode = "ko";
export const SUPPORTED_LOCALES: LocaleCode[] = ["ko", "en"];

export const LOCALES = {
  ko: koLocale,
  en: enLocale,
} as const;

export { koLocale, enLocale };
