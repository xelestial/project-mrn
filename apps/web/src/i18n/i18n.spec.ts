import { describe, expect, it } from "vitest";
import { resolveLocaleFromStoredValue } from "./I18nProvider";
import { DEFAULT_LOCALE, LOCALES, SUPPORTED_LOCALES } from "./index";

describe("i18n registry", () => {
  it("supports Korean and English", () => {
    expect(SUPPORTED_LOCALES).toEqual(["ko", "en"]);
    expect(DEFAULT_LOCALE).toBe("en");
  });

  it("keeps important locale sections aligned", () => {
    expect(LOCALES.ko.app.title).toBe("MRN");
    expect(LOCALES.en.app.routeLobby).toBe("Lobby");
    expect(LOCALES.ko.board.tileKind.T3).toBe(LOCALES.ko.board.tileKind.T2);
    expect(LOCALES.en.board.tileKind.T3).toBe(LOCALES.en.board.tileKind.T2);
    expect(LOCALES.en.board.tilePrice).toEqual({ purchase: "Buy", rent: "Rent", unit: "N" });
    expect(LOCALES.en.prompt.choice.buyTileTitle).toBe("Buy tile");
    expect(LOCALES.ko.prompt.context.burdenExchangeTrigger(3, 3.5)).toBe("보급 단계 (F 3.5 / 기준 3)");
    expect(LOCALES.en.prompt.context.burdenExchangeTrigger(3, 3.5)).toBe("Supply step (F 3.5 / threshold 3)");
    expect(LOCALES.ko.prompt.requestMetaPills(2, 30000, 18)).toEqual([
      "행동자 P2",
      "제한 30초",
      "남은 시간 18초",
    ]);
    expect(LOCALES.en.prompt.requestMetaPills(2, 30000, 18)).toEqual([
      "Actor P2",
      "Limit 30s",
      "18s left",
    ]);
    expect(LOCALES.ko.prompt.requestCompactMetaPills("player_public_5", 18)).toEqual([
      "player_public_5",
      "남은 18초",
    ]);
    expect(LOCALES.en.prompt.requestCompactMetaPills("player_public_5", 18)).toEqual([
      "player_public_5",
      "18s left",
    ]);
  });

  it("restores stored locale values and falls back to default", () => {
    expect(resolveLocaleFromStoredValue("ko")).toBe("ko");
    expect(resolveLocaleFromStoredValue("en")).toBe("en");
    expect(resolveLocaleFromStoredValue("jp")).toBe("en");
    expect(resolveLocaleFromStoredValue(null)).toBe("en");
  });
});
