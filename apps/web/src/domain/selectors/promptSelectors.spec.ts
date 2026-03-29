import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import { selectActivePrompt } from "./promptSelectors";

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
        choices: [{ choice_id: "roll", title: "굴리기", description: "일반 이동" }],
      },
    };
    const model = selectActivePrompt([promptMessage]);
    expect(model?.requestId).toBe("req_1");
    expect(model?.choices[0].choiceId).toBe("roll");
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
          choices: [{ choice_id: "roll", title: "굴리기", description: "일반 이동" }],
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
});

