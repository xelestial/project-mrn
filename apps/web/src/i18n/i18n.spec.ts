import { describe, expect, it } from "vitest";
import { resolveLocaleFromStoredValue } from "./I18nProvider";
import { DEFAULT_LOCALE, LOCALES, SUPPORTED_LOCALES } from "./index";

describe("i18n registry", () => {
  it("supports Korean and English", () => {
    expect(SUPPORTED_LOCALES).toEqual(["ko", "en"]);
    expect(DEFAULT_LOCALE).toBe("en");
  });

  it("keeps important locale sections aligned", () => {
    expect(LOCALES.ko.app.title).toBe("MRN Online Viewer (React/FastAPI)");
    expect(LOCALES.en.app.routeLobby).toBe("Lobby");
    expect(LOCALES.en.prompt.choice.buyTileTitle).toBe("Buy tile");
  });

  it("restores stored locale values and falls back to default", () => {
    expect(resolveLocaleFromStoredValue("ko")).toBe("ko");
    expect(resolveLocaleFromStoredValue("en")).toBe("en");
    expect(resolveLocaleFromStoredValue("jp")).toBe("en");
    expect(resolveLocaleFromStoredValue(null)).toBe("en");
  });
});
