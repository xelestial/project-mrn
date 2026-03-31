import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import { selectActivePrompt, selectLatestDecisionAck } from "./promptSelectors";

describe("promptSelectors", () => {
  it("returns active prompt when unresolved", () => {
    const promptMessage: InboundMessage = {
      type: "prompt",
      seq: 3,
      session_id: "s1",
      payload: {
        request_id: "req_1",
        request_type: "movement",
        player_id: 1,
        timeout_ms: 30000,
        choices: [{ choice_id: "roll", title: "주사위 굴리기", description: "일반 이동" }],
        public_context: { player_position: 0 },
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.requestId).toBe("req_1");
    expect(model?.choices[0].choiceId).toBe("roll");
    expect(model?.publicContext.player_position).toBe(0);
  });

  it("parses legal_choices fallback shape from server runtime prompts", () => {
    const promptMessage: InboundMessage = {
      type: "prompt",
      seq: 6,
      session_id: "s1",
      payload: {
        request_id: "req_legal_1",
        request_type: "trick_to_use",
        player_id: 1,
        timeout_ms: 300000,
        legal_choices: [
          {
            choice_id: "deck_12",
            label: "건강 검진",
            value: { card_description: "모든 참가자의 통행료를 절반으로 감소합니다." },
          },
        ],
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.requestId).toBe("req_legal_1");
    expect(model?.choices).toHaveLength(1);
    expect(model?.choices[0].choiceId).toBe("deck_12");
    expect(model?.choices[0].title).toBe("건강 검진");
    expect(model?.choices[0].description).toContain("통행료");
  });

  it("returns null when accepted ack exists for same request", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 3,
        session_id: "s1",
        payload: {
          request_id: "req_1",
          request_type: "movement",
          player_id: 1,
          timeout_ms: 30000,
          choices: [{ choice_id: "roll", title: "주사위 굴리기", description: "일반 이동" }],
        },
      },
      {
        type: "decision_ack",
        seq: 4,
        session_id: "s1",
        payload: { request_id: "req_1", status: "accepted", player_id: 1 },
      },
    ];
    expect(selectActivePrompt(messages)).toBeNull();
  });

  it("returns latest decision ack status for request id", () => {
    const messages: InboundMessage[] = [
      {
        type: "decision_ack",
        seq: 5,
        session_id: "s1",
        payload: { request_id: "req_1", status: "rejected", reason: "invalid_choice" },
      },
    ];
    const ack = selectLatestDecisionAck(messages, "req_1");
    expect(ack?.status).toBe("rejected");
    expect(ack?.reason).toBe("invalid_choice");
  });
});
