import { describe, expect, it } from "vitest";
import { toneForEventCode } from "./eventToneCatalog";

describe("eventToneCatalog", () => {
  it("maps move/economy/system/critical by event code only", () => {
    expect(toneForEventCode("player_move")).toBe("move");
    expect(toneForEventCode("tile_purchased")).toBe("economy");
    expect(toneForEventCode("bankruptcy")).toBe("critical");
    expect(toneForEventCode("custom_unknown")).toBe("system");
  });
});
