import { createContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { DEFAULT_LOCALE, LOCALES, SUPPORTED_LOCALES } from "./index";
import type { LocaleCode, LocaleMessages } from "./types";

const STORAGE_KEY = "mrn:web:locale";

export type I18nContextValue = {
  locale: LocaleCode;
  setLocale: (locale: LocaleCode) => void;
  messages: LocaleMessages;
};

export const I18nContext = createContext<I18nContextValue | null>(null);

function resolveInitialLocale(): LocaleCode {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en") {
    return "en";
  }
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(resolveInitialLocale);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale: (nextLocale) => setLocaleState(nextLocale),
      messages: LOCALES[locale],
    }),
    [locale]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
