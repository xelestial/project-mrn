import { describe, expect, it } from "vitest";
import { eventLabelForCode, nonEventLabelForMessageType } from "./eventLabelCatalog";

describe("eventLabelCatalog", () => {
  it("maps known event codes to readable labels", () => {
    expect(eventLabelForCode("round_start")).toBe("Round Start");
    expect(eventLabelForCode("dice_roll")).toBe("Move Decision");
  });

  it("falls back to raw event code when unknown", () => {
    expect(eventLabelForCode("custom_future_event")).toBe("custom_future_event");
  });

  it("maps non-event message types with safe fallback", () => {
    expect(nonEventLabelForMessageType("prompt")).toBe("Prompt");
    expect(nonEventLabelForMessageType("unknown_type")).toBe("Message");
  });
});
