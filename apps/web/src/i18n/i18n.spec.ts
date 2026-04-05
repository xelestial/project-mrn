import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, LOCALES, SUPPORTED_LOCALES } from "./index";

describe("i18n registry", () => {
  it("supports Korean and English", () => {
    expect(SUPPORTED_LOCALES).toEqual(["ko", "en"]);
    expect(DEFAULT_LOCALE).toBe("ko");
  });

  it("keeps important locale sections aligned", () => {
    expect(LOCALES.ko.app.title).toBe("MRN Online Viewer (React/FastAPI)");
    expect(LOCALES.en.app.routeLobby).toBe("Lobby");
    expect(LOCALES.ko.prompt.choice.buyTileTitle).toBe("토지 구매");
    expect(LOCALES.en.prompt.choice.buyTileTitle).toBe("Buy tile");
  });
});
