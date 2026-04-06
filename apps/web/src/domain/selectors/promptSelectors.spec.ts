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
        legal_choices: [{ choice_id: "roll", title: "주사위 굴리기", description: "일반 이동" }],
        public_context: { player_position: 0 },
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.requestId).toBe("req_1");
    expect(model?.choices[0].choiceId).toBe("roll");
    expect(model?.publicContext.player_position).toBe(0);
  });

  it("parses canonical legal_choices shape from server runtime prompts", () => {
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
            value: { card_description: "모든 참가자의 통행료를 절반으로 낮춥니다." },
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
    expect(model?.choices[0].secondary).toBe(false);
  });

  it("uses value.description when explicit description is omitted", () => {
    const promptMessage: InboundMessage = {
      type: "prompt",
      seq: 8,
      session_id: "s1",
      payload: {
        request_id: "req_pabal_1",
        request_type: "pabal_dice_mode",
        player_id: 1,
        timeout_ms: 300000,
        legal_choices: [
          {
            choice_id: "minus_one",
            label: "Roll one die",
            value: { description: "Reduce the roll to one die this turn." },
          },
        ],
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.requestType).toBe("pabal_dice_mode");
    expect(model?.choices[0].title).toBe("Roll one die");
    expect(model?.choices[0].description).toBe("Reduce the roll to one die this turn.");
  });

  it("marks passive canonical choices as secondary", () => {
    const promptMessage: InboundMessage = {
      type: "prompt",
      seq: 9,
      session_id: "s1",
      payload: {
        request_id: "req_purchase_1",
        request_type: "purchase_tile",
        player_id: 2,
        timeout_ms: 30000,
        legal_choices: [
          { choice_id: "yes", title: "Buy", description: "Buy the tile." },
          { choice_id: "no", title: "Skip", description: "Do not buy this tile." },
        ],
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.choices[0].secondary).toBe(false);
    expect(model?.choices[1].secondary).toBe(true);
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
          legal_choices: [{ choice_id: "roll", title: "주사위 굴리기", description: "일반 이동" }],
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

  it("returns null when decision_resolved event exists for same request without local ack", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 10,
        session_id: "s1",
        payload: {
          request_id: "req_passive_1",
          request_type: "purchase_tile",
          player_id: 2,
          timeout_ms: 30000,
          legal_choices: [{ choice_id: "yes", title: "buy", description: "buy tile" }],
        },
      },
      {
        type: "event",
        seq: 11,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          request_id: "req_passive_1",
          player_id: 2,
          resolution: "accepted",
          choice_id: "yes",
        },
      },
    ];
    expect(selectActivePrompt(messages)).toBeNull();
  });

  it("returns null when timeout fallback event closes the same prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 20,
        session_id: "s1",
        payload: {
          request_id: "req_timeout_1",
          request_type: "movement",
          player_id: 3,
          timeout_ms: 30000,
          legal_choices: [{ choice_id: "roll", title: "roll", description: "roll move" }],
        },
      },
      {
        type: "event",
        seq: 21,
        session_id: "s1",
        payload: {
          event_type: "decision_timeout_fallback",
          request_id: "req_timeout_1",
          player_id: 3,
          fallback_choice_id: "roll",
        },
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
