export type LocaleCode = "ko" | "en";

export type LocaleMessages =
  | typeof import("./locales/ko").koLocale
  | typeof import("./locales/en").enLocale;
