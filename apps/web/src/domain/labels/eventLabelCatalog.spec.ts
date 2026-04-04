import { describe, expect, it } from "vitest";
import { eventLabelForCode, nonEventLabelForMessageType } from "./eventLabelCatalog";

describe("eventLabelCatalog", () => {
  it("maps known event codes to human-readable labels", () => {
    expect(eventLabelForCode("round_start")).not.toBe("round_start");
    expect(eventLabelForCode("dice_roll")).not.toBe("dice_roll");
    expect(eventLabelForCode("decision_requested")).not.toBe("decision_requested");
    expect(eventLabelForCode("decision_resolved")).not.toBe("decision_resolved");
  });

  it("falls back to raw event code when unknown", () => {
    expect(eventLabelForCode("custom_future_event")).toBe("custom_future_event");
  });

  it("maps non-event message types with safe fallback", () => {
    expect(nonEventLabelForMessageType("prompt")).not.toBe("prompt");
    expect(nonEventLabelForMessageType("unknown_type")).toBe("메시지");
  });
});
