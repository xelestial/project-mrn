import { describe, expect, it } from "vitest";
import type { InboundMessage, ViewCommitPayload } from "../../core/contracts/stream";
import {
  selectActivePrompt,
  selectCurrentHandTrayCards,
  selectLatestDecisionAck,
  selectPromptInteractionState,
} from "./promptSelectors";

function viewCommit(commitSeq: number, viewState: Record<string, unknown>): InboundMessage {
  const payload: ViewCommitPayload = {
    schema_version: 1,
    commit_seq: commitSeq,
    source_event_seq: commitSeq + 100,
    viewer: { role: "seat", player_id: 2, seat: 2 },
    runtime: {
      status: "waiting_input",
      round_index: 3,
      turn_index: 1,
      active_frame_id: "turn:3:p2",
      active_module_id: "mod:turn:3:p2:mark",
      active_module_type: "MarkTargetModule",
      module_path: ["RoundModule", "TurnModule", "MarkTargetModule"],
    },
    view_state: viewState,
  };
  return {
    type: "view_commit",
    seq: commitSeq + 1000,
    session_id: "s1",
    server_time_ms: commitSeq + 2000,
    payload,
  };
}

describe("promptSelectors authoritative ViewCommit contract", () => {
  it("ignores raw prompt/event payloads even when they contain view_state-shaped data", () => {
    const rawPrompt: InboundMessage = {
      type: "prompt",
      seq: 1,
      session_id: "s1",
      payload: {
        request_id: "raw_prompt",
        request_type: "movement",
        player_id: 1,
        legal_choices: [{ choice_id: "roll", title: "roll" }],
        view_state: {
          prompt: {
            active: {
              request_id: "raw_projected_prompt",
              request_type: "movement",
              player_id: 1,
              choices: [{ choice_id: "roll", title: "roll" }],
            },
          },
          hand_tray: { items: [{ title: "raw card" }] },
        },
      },
    };
    const rawEvent: InboundMessage = {
      type: "event",
      seq: 2,
      session_id: "s1",
      payload: {
        event_type: "decision_resolved",
        view_state: {
          prompt: {
            last_feedback: {
              request_id: "raw_projected_prompt",
              status: "accepted",
              reason: "",
            },
          },
        },
      },
    };

    expect(selectActivePrompt([rawPrompt, rawEvent])).toBeNull();
    expect(selectLatestDecisionAck([rawPrompt, rawEvent], "raw_projected_prompt")).toBeNull();
    expect(selectCurrentHandTrayCards([rawPrompt, rawEvent], "ko", 1)).toEqual([]);
  });

  it("renders the active prompt only from latest ViewCommit.view_state.prompt.active", () => {
    const messages = [
      viewCommit(4, {
        prompt: {
          active: {
            request_id: "req_mark",
            request_type: "mark_target",
            player_id: 2,
            timeout_ms: 30000,
            runner_kind: "module",
            resume_token: "resume_1",
            frame_id: "turn:3:p2",
            module_id: "mod:turn:3:p2:mark",
            module_type: "MarkTargetModule",
            module_cursor: "mark:await_target",
            batch_id: "batch_1",
            prompt_instance_id: 17,
            choices: [
              {
                choice_id: "target_p1",
                title: "박수",
                description: "박수를 지목합니다.",
                value: { target_player_id: 1, target_character: "박수", target_card_no: 3 },
              },
              {
                choice_id: "none",
                title: "넘김",
                description: "지목하지 않습니다.",
                value: { target_player_id: null },
              },
            ],
            public_context: { actor_name: "산적", card_deck_index: 22 },
            behavior: {
              normalized_request_type: "mark_target",
              single_surface: true,
              auto_continue: false,
              chain_key: "mark",
              chain_item_count: 2,
              current_item_deck_index: 22,
            },
            surface: {
              kind: "mark_target",
              blocks_public_events: true,
              mark_target: {
                actor_name: "산적",
                none_choice_id: "none",
                candidates: [
                  {
                    choice_id: "target_p1",
                    target_character: "박수",
                    target_card_no: 3,
                    target_player_id: 1,
                  },
                ],
              },
            },
            effect_context: {
              label: "산적",
              detail: "산적의 지목 효과를 처리합니다.",
              attribution: "인물 지목",
              tone: "effect",
              source: "character",
              intent: "mark",
              enhanced: true,
              source_player_id: 2,
              source_family: "character",
              source_name: "산적",
              resource_delta: { cash: -3 },
            },
          },
        },
      }),
      {
        type: "prompt",
        seq: 999,
        session_id: "s1",
        payload: {
          request_id: "raw_later_prompt",
          request_type: "movement",
          player_id: 1,
          legal_choices: [{ choice_id: "roll", title: "roll" }],
        },
      } satisfies InboundMessage,
    ];

    const prompt = selectActivePrompt(messages);

    expect(prompt?.requestId).toBe("req_mark");
    expect(prompt?.requestType).toBe("mark_target");
    expect(prompt?.playerId).toBe(2);
    expect(prompt?.choices.map((choice) => choice.choiceId)).toEqual(["target_p1", "none"]);
    expect(prompt?.continuation).toEqual({
      promptInstanceId: 17,
      resumeToken: "resume_1",
      frameId: "turn:3:p2",
      moduleId: "mod:turn:3:p2:mark",
      moduleType: "MarkTargetModule",
      moduleCursor: "mark:await_target",
      batchId: "batch_1",
    });
    expect(prompt?.behavior).toMatchObject({
      normalizedRequestType: "mark_target",
      singleSurface: true,
      chainKey: "mark",
      currentItemDeckIndex: 22,
    });
    expect(prompt?.surface.markTarget?.candidates).toEqual([
      {
        choiceId: "target_p1",
        targetCharacter: "박수",
        targetCardNo: 3,
        targetPlayerId: 1,
      },
    ]);
    expect(prompt?.effectContext).toEqual({
      label: "산적",
      detail: "산적의 지목 효과를 처리합니다.",
      attribution: "인물 지목",
      tone: "effect",
      source: "character",
      intent: "mark",
      enhanced: true,
      sourcePlayerId: 2,
      sourceFamily: "character",
      sourceName: "산적",
      resourceDelta: { cash: -3 },
    });
  });

  it("does not expose a module prompt unless the ViewCommit contains complete continuation data", () => {
    const incomplete = viewCommit(1, {
      prompt: {
        active: {
          request_id: "req_incomplete",
          request_type: "movement",
          player_id: 1,
          runner_kind: "module",
          resume_token: "resume_1",
          frame_id: "turn:1:p1",
          module_id: "mod:move",
          module_type: "MapMoveModule",
          choices: [{ choice_id: "roll", title: "roll" }],
        },
      },
    });
    const complete = viewCommit(2, {
      prompt: {
        active: {
          request_id: "req_complete",
          request_type: "movement",
          player_id: 1,
          runner_kind: "module",
          resume_token: "resume_2",
          frame_id: "turn:1:p1",
          module_id: "mod:move",
          module_type: "MapMoveModule",
          module_cursor: "movement:await_choice",
          choices: [{ choice_id: "roll", title: "roll" }],
        },
      },
    });

    expect(selectActivePrompt([incomplete])).toBeNull();
    expect(selectActivePrompt([complete])?.continuation.moduleCursor).toBe("movement:await_choice");
  });

  it("reads prompt feedback and hand tray only from ViewCommit.view_state", () => {
    const messages = [
      {
        type: "decision_ack",
        seq: 1,
        session_id: "s1",
        payload: { request_id: "req_hand", status: "accepted", reason: "raw ack" },
      } satisfies InboundMessage,
      viewCommit(3, {
        prompt: {
          last_feedback: {
            request_id: "req_hand",
            status: "stale",
            reason: "stale commit",
          },
        },
        hand_tray: {
          items: [
            {
              key: "trick-7",
              title: "잔꾀",
              effect: "추가 선택",
              serial: "T007",
              hidden: false,
              is_current_target: true,
            },
          ],
        },
      }),
    ];

    expect(selectLatestDecisionAck(messages, "req_hand")).toEqual({
      status: "stale",
      reason: "stale commit",
    });
    expect(selectCurrentHandTrayCards(messages, "ko", 2)).toEqual([
      {
        key: "trick-7",
        title: "잔꾀",
        effect: "추가 선택",
        serial: "T007",
        hidden: false,
        currentTarget: true,
      },
    ]);
  });

  it("derives prompt interaction feedback from authoritative prompt feedback only", () => {
    const messages = [
      viewCommit(3, {
        prompt: {
          active: {
            request_id: "req_move",
            request_type: "movement",
            player_id: 1,
            choices: [{ choice_id: "roll", title: "roll" }],
          },
          last_feedback: {
            request_id: "req_move",
            status: "rejected",
            reason: "invalid choice",
          },
        },
      }),
    ];
    const activePrompt = selectActivePrompt(messages);

    expect(
      selectPromptInteractionState({
        messages,
        activePrompt,
        trackedRequestId: "req_move",
        submitting: true,
        expiresAtMs: 10_000,
        nowMs: 5_000,
        streamStatus: "connected",
      })
    ).toMatchObject({
      requestId: "req_move",
      shouldReleaseSubmission: true,
      feedback: { kind: "rejected", reason: "invalid choice" },
    });
  });
});
