import { describe, expect, it } from "vitest";
import { eventLabelForCode, nonEventLabelForMessageType } from "./eventLabelCatalog";

describe("eventLabelCatalog", () => {
  it("maps known event codes to readable labels", () => {
    expect(eventLabelForCode("round_start")).toBe("라운드 시작");
    expect(eventLabelForCode("dice_roll")).toBe("이동값 결정");
  });

  it("falls back to raw event code when unknown", () => {
    expect(eventLabelForCode("custom_future_event")).toBe("custom_future_event");
  });

  it("maps non-event message types with safe fallback", () => {
    expect(nonEventLabelForMessageType("prompt")).toBe("선택 요청");
    expect(nonEventLabelForMessageType("unknown_type")).toBe("메시지");
  });
});
