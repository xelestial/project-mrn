import { describe, expect, it } from "vitest";
import { eventLabelForCode, nonEventLabelForMessageType } from "./eventLabelCatalog";

describe("eventLabelCatalog", () => {
  it("maps known event codes to Korean labels", () => {
    expect(eventLabelForCode("round_start")).toBe("라운드 시작");
    expect(eventLabelForCode("decision_requested")).toBe("선택 요청 등록");
    expect(eventLabelForCode("decision_resolved")).toBe("선택 처리 완료");
  });

  it("falls back to the original event code for unknown values", () => {
    expect(eventLabelForCode("custom_event")).toBe("custom_event");
  });

  it("maps non-event message types", () => {
    expect(nonEventLabelForMessageType("prompt")).toBe("선택 요청");
    expect(nonEventLabelForMessageType("decision_ack")).toBe("선택 응답");
  });

  it("falls back to generic message label", () => {
    expect(nonEventLabelForMessageType("")).toBe("메시지");
    expect(nonEventLabelForMessageType("unknown")).toBe("메시지");
  });
});
