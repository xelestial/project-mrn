import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import {
  DEBUG_TURN_SELECTION_ALL,
  groupDebugMessagesByTurn,
  selectDebugMessagesForTurn,
} from "./debugLogSelectors";

function event(seq: number, payload: Record<string, unknown>): InboundMessage {
  return { type: "event", seq, session_id: "s1", payload };
}

describe("debugLogSelectors", () => {
  it("accumulates messages into selectable round and turn groups", () => {
    const groups = groupDebugMessagesByTurn(
      [
        event(1, { event_type: "turn_start", round_index: 1, turn_index: 1 }),
        event(2, { event_type: "dice_roll", round_index: 1, turn_index: 1 }),
        event(3, { event_type: "turn_start", round_index: 1, turn_index: 2 }),
        event(4, { event_type: "turn_start", round_index: 2, turn_index: 1 }),
      ],
      "ko"
    );

    expect(groups.map((group) => group.label)).toEqual(["1라운드 / 1턴", "1라운드 / 2턴", "2라운드 / 1턴"]);
    expect(groups.map((group) => group.messages.map((message) => message.seq))).toEqual([[1, 2], [3], [4]]);
  });

  it("uses prompt public_context metadata when top-level fields are absent", () => {
    const groups = groupDebugMessagesByTurn(
      [
        event(1, { event_type: "turn_start", round_index: 4, turn_index: 8 }),
        event(2, { request_type: "choose_purchase_tile", public_context: { round_index: 4, turn_index: 8 } }),
      ],
      "en"
    );

    expect(groups).toHaveLength(1);
    expect(groups[0]?.label).toBe("Round 4 / Turn 8");
    expect(groups[0]?.messages.map((message) => message.seq)).toEqual([1, 2]);
  });

  it("hides synthetic restored view-state messages from user-facing debug groups", () => {
    const messages = [
      event(1, { event_type: "turn_start", round_index: 4, turn_index: 8 }),
      event(2, { event_type: "view_state_restored", view_state: { turn_stage: { round_index: 4, turn_index: 8 } } }),
      event(3, { event_type: "dice_roll", round_index: 4, turn_index: 8 }),
    ];
    const groups = groupDebugMessagesByTurn(messages, "en");

    expect(groups).toHaveLength(1);
    expect(groups[0]?.messages.map((message) => message.seq)).toEqual([1, 3]);
    expect(selectDebugMessagesForTurn(messages, groups, DEBUG_TURN_SELECTION_ALL).map((message) => message.seq)).toEqual([
      1,
      3,
    ]);
  });

  it("filters messages by a previous round and turn selection without dropping the full log", () => {
    const messages = [
      event(1, { event_type: "turn_start", round_index: 1, turn_index: 1 }),
      event(2, { event_type: "dice_roll", round_index: 1, turn_index: 1 }),
      event(3, { event_type: "turn_start", round_index: 1, turn_index: 2 }),
    ];
    const groups = groupDebugMessagesByTurn(messages, "en");

    expect(selectDebugMessagesForTurn(messages, groups, groups[0]?.key ?? "")).toEqual(messages.slice(0, 2));
    expect(selectDebugMessagesForTurn(messages, groups, DEBUG_TURN_SELECTION_ALL)).toEqual(messages);
  });
});
