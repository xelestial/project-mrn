import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { InboundMessage } from "../../core/contracts/stream";
import {
  selectActivePrompt,
  selectCurrentHandTrayCards,
  selectLatestDecisionAck,
  selectPromptInteractionState,
} from "./promptSelectors";

function loadSharedPromptFixture(filename: string) {
  const path = resolve(process.cwd(), "../../packages/runtime-contracts/ws/examples", filename);
  return JSON.parse(readFileSync(path, "utf-8")) as {
    messages: InboundMessage[];
    expected: {
      prompt: {
        active: {
          surface: Record<string, unknown>;
        };
      };
    };
  };
}

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

  it("prefers the latest state-bearing prompt over an older backend-projected prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          view_state: {
            prompt: {
              active: {
                request_id: "req_backend_prompt_1",
                request_type: "purchase_tile",
                player_id: 2,
                timeout_ms: 45000,
                choices: [
                  {
                    choice_id: "yes",
                    title: "Buy tile",
                    description: "Purchase the landed tile.",
                    value: { tile_index: 8 },
                    secondary: false,
                  },
                  {
                    choice_id: "no",
                    title: "Skip",
                    description: "End turn without buying.",
                    value: null,
                    secondary: true,
                  },
                ],
                public_context: {
                  tile_index: 8,
                  tile_purchase_cost: 4,
                },
              },
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_old_prompt",
          request_type: "movement",
          player_id: 1,
          timeout_ms: 30000,
          legal_choices: [{ choice_id: "roll", title: "roll", description: "roll move" }],
        },
      },
    ];

    const model = selectActivePrompt(messages);
    expect(model?.requestId).toBe("req_old_prompt");
    expect(model?.requestType).toBe("movement");
    expect(model?.playerId).toBe(1);
  });

  it("does not let an older backend view_state suppress a newer raw prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          view_state: {
            players: {
              ordered_player_ids: [1, 2],
              marker_owner_player_id: 1,
              marker_draft_direction: "clockwise",
              items: [],
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_old_prompt",
          request_type: "movement",
          player_id: 1,
          timeout_ms: 30000,
          legal_choices: [{ choice_id: "roll", title: "roll", description: "roll move" }],
        },
      },
    ];

    expect(selectActivePrompt(messages)).toMatchObject({
      requestId: "req_old_prompt",
      requestType: "movement",
      playerId: 1,
    });
  });

  it("projects backend prompt behavior for burden exchange chain handling", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          view_state: {
            prompt: {
              active: {
                request_id: "req_burden_1",
                request_type: "burden_exchange",
                player_id: 1,
                timeout_ms: 30000,
                choices: [
                  { choice_id: "yes", title: "Pay 2 to remove", description: "", value: null, secondary: false },
                  { choice_id: "no", title: "Keep burden", description: "", value: null, secondary: true },
                ],
                public_context: {
                  card_deck_index: 91,
                  burden_card_count: 3,
                },
                behavior: {
                  normalized_request_type: "burden_exchange_batch",
                  single_surface: true,
                  auto_continue: true,
                  chain_key: "burden_exchange:1:3",
                  chain_item_count: 3,
                  current_item_deck_index: 91,
                },
              },
            },
          },
        },
      },
    ];

    const model = selectActivePrompt(messages);
    expect(model?.behavior).toEqual({
      normalizedRequestType: "burden_exchange_batch",
      singleSurface: true,
      autoContinue: true,
      chainKey: "burden_exchange:1:3",
      chainItemCount: 3,
      currentItemDeckIndex: 91,
    });
    expect(model?.surface.kind).toBe("burden_exchange");
    expect(model?.surface.blocksPublicEvents).toBe(true);
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

  it("returns null when a later draft_pick already completed the same player's draft prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 30,
        session_id: "s1",
        payload: {
          request_id: "req_draft_1",
          request_type: "draft_card",
          player_id: 1,
          timeout_ms: 300000,
          legal_choices: [{ choice_id: "card_1", title: "중매꾼", description: "pick" }],
        },
      },
      {
        type: "event",
        seq: 31,
        session_id: "s1",
        payload: {
          event_type: "draft_pick",
          acting_player_id: 1,
          draft_phase: 1,
          picked_card: "중매꾼",
        },
      },
    ];
    expect(selectActivePrompt(messages)).toBeNull();
  });

  it("keeps draft phase and option count on character pick prompts", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 30,
        session_id: "s1",
        payload: {
          request_id: "req_draft_phase_2",
          request_type: "draft_card",
          player_id: 3,
          timeout_ms: 300000,
          legal_choices: [{ choice_id: "card_8", title: "만신", description: "pick" }],
          public_context: { draft_phase: 2, draft_phase_label: "draft_phase_2", offered_count: 1 },
          view_state: {
            prompt: {
              active: {
                request_id: "req_draft_phase_2",
                request_type: "draft_card",
                player_id: 3,
                timeout_ms: 300000,
                choices: [{ choice_id: "card_8", title: "만신", description: "pick", value: null, secondary: false }],
                public_context: { draft_phase: 2, draft_phase_label: "draft_phase_2", offered_count: 1 },
                behavior: {
                  normalized_request_type: "draft_card",
                  single_surface: false,
                  auto_continue: false,
                },
                surface: {
                  kind: "character_pick",
                  blocks_public_events: true,
                  character_pick: {
                    phase: "draft",
                    draft_phase: 2,
                    draft_phase_label: "draft_phase_2",
                    choice_count: 1,
                    options: [{ choice_id: "card_8", name: "만신", description: "pick" }],
                  },
                },
              },
            },
          },
        },
      },
    ];

    expect(selectActivePrompt(messages)?.surface.characterPick).toMatchObject({
      phase: "draft",
      draftPhase: 2,
      draftPhaseLabel: "draft_phase_2",
      choiceCount: 1,
    });
  });

  it("returns null when a later final_character_choice already completed the same player's final selection prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 40,
        session_id: "s1",
        payload: {
          request_id: "req_final_1",
          request_type: "final_character",
          player_id: 1,
          timeout_ms: 300000,
          legal_choices: [{ choice_id: "만신", title: "만신", description: "pick" }],
        },
      },
      {
        type: "event",
        seq: 41,
        session_id: "s1",
        payload: {
          event_type: "final_character_choice",
          acting_player_id: 1,
          character: "만신",
        },
      },
    ];
    expect(selectActivePrompt(messages)).toBeNull();
  });

  it("returns null when a later trick_used already completed the same player's trick prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 50,
        session_id: "s1",
        payload: {
          request_id: "req_trick_1",
          request_type: "trick_to_use",
          player_id: 1,
          timeout_ms: 300000,
          legal_choices: [{ choice_id: "42", title: "긴장감 조성", description: "rent double" }],
        },
      },
      {
        type: "event",
        seq: 51,
        session_id: "s1",
        payload: {
          event_type: "trick_used",
          acting_player_id: 1,
          card_name: "긴장감 조성",
        },
      },
    ];
    expect(selectActivePrompt(messages)).toBeNull();
  });

  it("uses a newer raw prompt when the latest backend view_state is stale", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          view_state: {
            prompt: {},
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_mark_live",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [{ choice_id: "none", title: "지목 안 함" }],
          public_context: { actor_name: "산적" },
        },
      },
    ];

    expect(selectActivePrompt(messages)).toMatchObject({
      requestId: "req_mark_live",
      requestType: "mark_target",
      playerId: 1,
    });
  });

  it("does not keep an old backend prompt active after a newer raw closing event", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 1,
        session_id: "s1",
        payload: {
          request_id: "req_draft_live",
          request_type: "draft_card",
          player_id: 1,
          legal_choices: [{ choice_id: "card_1", title: "중매꾼" }],
          view_state: {
            prompt: {
              active: {
                request_id: "req_draft_live",
                request_type: "draft_card",
                player_id: 1,
                timeout_ms: 300000,
                choices: [{ choice_id: "card_1", title: "중매꾼", description: "", value: null, secondary: false }],
                public_context: {},
                behavior: {
                  normalized_request_type: "draft_card",
                  single_surface: false,
                  auto_continue: false,
                },
                surface: {
                  kind: "character_pick",
                  blocks_public_events: true,
                  character_pick: {
                    phase: "draft",
                    options: [{ choice_id: "card_1", name: "중매꾼", description: "" }],
                  },
                },
              },
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "draft_pick",
          acting_player_id: 1,
          picked_card: "중매꾼",
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

  it("prefers the latest state-bearing prompt feedback over an older backend projection", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          view_state: {
            prompt: {
              last_feedback: {
                request_id: "req_1",
                status: "stale",
                reason: "request_superseded",
              },
            },
          },
        },
      },
      {
        type: "decision_ack",
        seq: 2,
        session_id: "s1",
        payload: { request_id: "req_1", status: "rejected", reason: "old_client_copy" },
      },
    ];

    const ack = selectLatestDecisionAck(messages, "req_1");
    expect(ack).toEqual({
      status: "rejected",
      reason: "old_client_copy",
    });
  });

  it("projects prompt interaction state from backend feedback and releases busy submission", () => {
    const prompt = {
      requestId: "req_1",
      requestType: "movement",
      playerId: 1,
      timeoutMs: 30000,
      choices: [],
      publicContext: {},
      behavior: {
        normalizedRequestType: "movement",
        singleSurface: false,
        autoContinue: false,
        chainKey: null,
        chainItemCount: null,
        currentItemDeckIndex: null,
      },
      surface: {
        kind: "movement",
        blocksPublicEvents: true,
        movement: null,
        lapReward: null,
        burdenExchangeBatch: null,
        markTarget: null,
        characterPick: null,
        handChoice: null,
        purchaseTile: null,
        trickTileTarget: null,
        coinPlacement: null,
        doctrineRelief: null,
        geoBonus: null,
        specificTrickReward: null,
        pabalDiceMode: null,
        runawayStep: null,
        activeFlip: null,
      },
    };
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          view_state: {
            prompt: {
              last_feedback: {
                request_id: "req_1",
                status: "rejected",
                reason: "invalid_choice",
              },
            },
          },
        },
      },
    ];

    const interaction = selectPromptInteractionState({
      messages,
      activePrompt: prompt,
      trackedRequestId: "req_1",
      submitting: true,
      expiresAtMs: Date.now() + 10_000,
      nowMs: Date.now(),
      streamStatus: "connected",
    });

    expect(interaction.busy).toBe(false);
    expect(interaction.shouldReleaseSubmission).toBe(true);
    expect(interaction.feedback).toEqual({
      kind: "rejected",
      reason: "invalid_choice",
    });
  });

  it("projects connection lost feedback while a prompt submission is in flight", () => {
    const interaction = selectPromptInteractionState({
      messages: [],
      activePrompt: {
        requestId: "req_2",
        requestType: "movement",
        playerId: 1,
        timeoutMs: 30000,
        choices: [],
        publicContext: {},
        behavior: {
          normalizedRequestType: "movement",
          singleSurface: false,
          autoContinue: false,
          chainKey: null,
          chainItemCount: null,
          currentItemDeckIndex: null,
        },
        surface: {
          kind: "movement",
          blocksPublicEvents: true,
          movement: null,
          lapReward: null,
          burdenExchangeBatch: null,
          markTarget: null,
          characterPick: null,
          handChoice: null,
          purchaseTile: null,
          trickTileTarget: null,
          coinPlacement: null,
          doctrineRelief: null,
          geoBonus: null,
          specificTrickReward: null,
          pabalDiceMode: null,
          runawayStep: null,
          activeFlip: null,
        },
      },
      trackedRequestId: "req_2",
      submitting: true,
      expiresAtMs: Date.now() + 10_000,
      nowMs: Date.now(),
      streamStatus: "disconnected",
    });

    expect(interaction.busy).toBe(false);
    expect(interaction.shouldReleaseSubmission).toBe(true);
    expect(interaction.feedback).toEqual({ kind: "connection_lost" });
  });

  it("projects timeout feedback when the active prompt expires locally", () => {
    const interaction = selectPromptInteractionState({
      messages: [],
      activePrompt: {
        requestId: "req_3",
        requestType: "movement",
        playerId: 1,
        timeoutMs: 30000,
        choices: [],
        publicContext: {},
        behavior: {
          normalizedRequestType: "movement",
          singleSurface: false,
          autoContinue: false,
          chainKey: null,
          chainItemCount: null,
          currentItemDeckIndex: null,
        },
        surface: {
          kind: "movement",
          blocksPublicEvents: true,
          movement: null,
          lapReward: null,
          burdenExchangeBatch: null,
          markTarget: null,
          characterPick: null,
          handChoice: null,
          purchaseTile: null,
          trickTileTarget: null,
          coinPlacement: null,
          doctrineRelief: null,
          geoBonus: null,
          specificTrickReward: null,
          pabalDiceMode: null,
          runawayStep: null,
          activeFlip: null,
        },
      },
      trackedRequestId: "req_3",
      submitting: false,
      expiresAtMs: 1_000,
      nowMs: 2_000,
      streamStatus: "connected",
    });

    expect(interaction.secondsLeft).toBe(0);
    expect(interaction.feedback).toEqual({ kind: "timed_out" });
  });

  it("builds the current hand tray from the active local prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 30,
        session_id: "s1",
        payload: {
          request_id: "req_trick_1",
          request_type: "trick_to_use",
          player_id: 1,
          timeout_ms: 30000,
          public_context: {
            full_hand: [
              {
                deck_index: 11,
                name: "건강 검진",
                card_description: "통행료를 절반으로 낮춥니다.",
                is_hidden: false,
              },
              {
                deck_index: 12,
                name: "뒷거래",
                card_description: "현금을 얻습니다.",
                is_hidden: true,
                is_current_target: true,
              },
            ],
          },
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([
      {
        key: "11-건강 검진",
        title: "건강 검진",
        effect: "통행료를 절반으로 낮춥니다.",
        serial: "#11",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "12-뒷거래",
        title: "뒷거래",
        effect: "현금을 얻습니다.",
        serial: "#12",
        hidden: true,
        currentTarget: true,
      },
    ]);
  });

  it("shows public trick hand from player state before the first local prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "session_start",
          players: [
            {
              player_id: 1,
              public_tricks: ["무거운 짐", "가벼운 짐", "월척회", "화목 난로"],
              hidden_trick_count: 1,
            },
          ],
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([
      {
        key: "public-1-0-무거운 짐",
        title: "무거운 짐",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "public-1-1-가벼운 짐",
        title: "가벼운 짐",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "public-1-2-월척회",
        title: "월척회",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "public-1-3-화목 난로",
        title: "화목 난로",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "hidden-1-0",
        title: "비공개 잔꾀",
        effect: "아직 공개되지 않은 잔꾀입니다.",
        serial: "",
        hidden: true,
        currentTarget: false,
      },
    ]);
  });

  it("does not add a phantom hidden trick before hidden selection when five public tricks are visible", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "session_start",
          players: [
            {
              player_id: 1,
              public_tricks: ["무거운 짐", "가벼운 짐", "월척회", "화목 난로", "건강 검진"],
              hidden_trick_count: 1,
            },
          ],
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toHaveLength(5);
  });

  it("keeps the initial setup trick hand visible during draft prompts", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "initial_public_tricks",
          players: [
            {
              player: 1,
              public_tricks: ["월척회", "건강 검진"],
              hidden_trick_count: 1,
            },
          ],
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_draft_1",
          request_type: "draft_card",
          player_id: 1,
          timeout_ms: 300000,
          public_context: {
            draft_phase: 1,
            offered_count: 4,
          },
          choices: [{ choice_id: "draft_mansin", title: "만신", description: "pick" }],
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([
      {
        key: "public-1-0-월척회",
        title: "월척회",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "public-1-1-건강 검진",
        title: "건강 검진",
        effect: "공개된 잔꾀입니다.",
        serial: "",
        hidden: false,
        currentTarget: false,
      },
      {
        key: "hidden-1-0",
        title: "비공개 잔꾀",
        effect: "아직 공개되지 않은 잔꾀입니다.",
        serial: "",
        hidden: true,
        currentTarget: false,
      },
    ]);
  });

  it("prefers the latest state-bearing hand tray over an older backend projection", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          view_state: {
            hand_tray: {
              cards: [
                {
                  key: "11-health-check",
                  name: "건강 검진",
                  description: "통행료를 절반으로 낮춥니다.",
                  deck_index: 11,
                  is_hidden: false,
                  is_current_target: false,
                },
              ],
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_trick_1",
          request_type: "trick_to_use",
          player_id: 1,
          timeout_ms: 30000,
          public_context: {
            full_hand: [
              {
                deck_index: 99,
                name: "오래된 카드",
                card_description: "오래된 손패 fallback",
              },
            ],
          },
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([
      {
        key: "99-오래된 카드",
        title: "오래된 카드",
        effect: "오래된 손패 fallback",
        serial: "#99",
        hidden: false,
        currentTarget: false,
      },
    ]);
  });

  it("treats an empty current backend hand tray as authoritative", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 1,
        session_id: "s1",
        payload: {
          request_id: "req_trick_1",
          request_type: "trick_to_use",
          player_id: 1,
          timeout_ms: 30000,
          public_context: {
            full_hand: [
              {
                deck_index: 77,
                name: "소비된 잔꾀",
                card_description: "이미 사용된 카드입니다.",
              },
            ],
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          view_state: {
            hand_tray: {
              cards: [],
            },
          },
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([]);
  });

  it("matches shared selector prompt lap reward surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.lap_reward_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.lapReward).toEqual({
      budget: 10,
      cashPool: 30,
      shardsPool: 18,
      coinsPool: 18,
      cashPointCost: 2,
      shardsPointCost: 3,
      coinsPointCost: 3,
      options: [
        { choiceId: "cash-2_shards-1_coins-1", cashUnits: 2, shardUnits: 1, coinUnits: 1, spentPoints: 10 },
        { choiceId: "cash-5_shards-0_coins-0", cashUnits: 5, shardUnits: 0, coinUnits: 0, spentPoints: 10 },
        { choiceId: "cash-2_shards-2_coins-0", cashUnits: 2, shardUnits: 2, coinUnits: 0, spentPoints: 10 },
      ],
    });
  });

  it("matches shared selector prompt burden surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.burden_exchange_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.burdenExchangeBatch).toEqual({
      burdenCardCount: 3,
      currentFValue: 3,
      supplyThreshold: 3,
      cards: [
        { deckIndex: 91, name: "무거운 짐", description: "이동 -1", burdenCost: 4, isCurrentTarget: true },
        { deckIndex: 92, name: "가벼운 짐", description: "효과 없음", burdenCost: 2, isCurrentTarget: false },
        { deckIndex: 93, name: "호객꾼", description: "말 효과", burdenCost: 2, isCurrentTarget: false },
      ],
    });
  });

  it("matches shared selector prompt mark target surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.mark_target_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.markTarget).toEqual({
      actorName: "산적",
      noneChoiceId: "none",
      candidates: [
        { choiceId: "교리 감독관", targetCharacter: "교리 감독관", targetCardNo: 5, targetPlayerId: null },
        { choiceId: "만신", targetCharacter: "만신", targetCardNo: 6, targetPlayerId: null },
        { choiceId: "객주", targetCharacter: "객주", targetCardNo: 7, targetPlayerId: null },
      ],
    });
  });

  it("matches shared selector prompt active flip surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.active_flip_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.activeFlip).toEqual({
      finishChoiceId: "none",
      options: [
        { choiceId: "5", cardIndex: 5, currentName: "교리 감독관", flippedName: "교리 연구관" },
        { choiceId: "7", cardIndex: 7, currentName: "객주", flippedName: "중매꾼" },
      ],
    });
  });

  it("matches shared selector prompt coin placement surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.coin_placement_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.coinPlacement).toEqual({
      ownedTileCount: 3,
      options: [
        { choiceId: "12", tileIndex: 12, title: "Tile 12", description: "Place one score point on tile 12." },
        { choiceId: "18", tileIndex: 18, title: "Tile 18", description: "Place one score point on tile 18." },
        { choiceId: "24", tileIndex: 24, title: "Tile 24", description: "Place one score point on tile 24." },
      ],
    });
  });

  it("matches shared selector prompt movement surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.movement_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.movement).toEqual({
      rollChoiceId: "dice",
      cardPool: [2, 5],
      canUseTwoCards: true,
      cardChoices: [
        { choiceId: "card_2", cards: [2], title: "Use card 2", description: "Move with card 2." },
        { choiceId: "card_5", cards: [5], title: "Use card 5", description: "Move with card 5." },
        { choiceId: "card_2_5", cards: [2, 5], title: "Use cards 2+5", description: "Move with cards 2 and 5." },
      ],
    });
  });

  it("matches shared selector prompt hand choice surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.hand_choice_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.handChoice).toEqual({
      mode: "use",
      passChoiceId: "none",
      cards: [
        { choiceId: "12", deckIndex: 12, name: "뇌고왕", description: "즉시 사용 효과", isHidden: false, isUsable: true },
        { choiceId: "17", deckIndex: 17, name: "객주", description: "상황 대응 카드", isHidden: false, isUsable: true },
        { choiceId: null, deckIndex: 25, name: "호객꾼", description: "숨긴 카드", isHidden: true, isUsable: false },
      ],
    });
  });

  it("matches shared selector prompt runaway step surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.runaway_step_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.runawayStep).toEqual({
      bonusChoiceId: "yes",
      stayChoiceId: "no",
      oneShortPos: 17,
      bonusTargetPos: 18,
      bonusTargetKind: "운수",
    });
  });

  it("matches shared selector prompt geo bonus surface fixture", () => {
    const fixture = loadSharedPromptFixture("selector.prompt.geo_bonus_surface.json");
    const messages = fixture.messages.map((message, index, items) =>
      index === items.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                prompt: {
                  active: {
                    ...(message.payload as Record<string, unknown>),
                    choices: (message.payload as Record<string, unknown>).legal_choices,
                    surface: fixture.expected.prompt.active.surface,
                  },
                },
              },
            },
          }
        : message
    );

    const model = selectActivePrompt(messages);
    expect(model?.surface.geoBonus).toEqual({
      actorName: "박수",
      options: [
        { choiceId: "cash", rewardKind: "cash", title: "Cash +1", description: "Gain 1 cash." },
        { choiceId: "shards", rewardKind: "shards", title: "Shards +1", description: "Gain 1 shard." },
        { choiceId: "coins", rewardKind: "coins", title: "Coins +1", description: "Gain 1 score point." },
      ],
    });
  });

  it("parses backend projected doctrine relief surface", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          view_state: {
            prompt: {
              active: {
                request_id: "req_doctrine",
                request_type: "doctrine_relief",
                player_id: 1,
                timeout_ms: 30000,
                choices: [
                  {
                    choice_id: "2",
                    title: "P2",
                    description: "Remove 1 burden from P2.",
                    value: { target_player_id: 2, burden_count: 1 },
                    secondary: false,
                  },
                ],
                public_context: { candidate_count: 1 },
                behavior: { normalized_request_type: "doctrine_relief", single_surface: false, auto_continue: false },
                surface: {
                  kind: "doctrine_relief",
                  blocks_public_events: true,
                  doctrine_relief: {
                    candidate_count: 1,
                    options: [
                      {
                        choice_id: "2",
                        target_player_id: 2,
                        burden_count: 1,
                        title: "P2",
                        description: "Remove 1 burden from P2.",
                      },
                    ],
                  },
                },
              },
            },
          },
        },
      },
    ];

    expect(selectActivePrompt(messages)?.surface.doctrineRelief).toEqual({
      candidateCount: 1,
      options: [{ choiceId: "2", targetPlayerId: 2, burdenCount: 1, title: "P2", description: "Remove 1 burden from P2." }],
    });
  });

  it("parses backend projected specific trick reward and pabal dice mode surfaces", () => {
    const rewardMessages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          view_state: {
            prompt: {
              active: {
                request_id: "req_reward",
                request_type: "specific_trick_reward",
                player_id: 1,
                timeout_ms: 30000,
                choices: [
                  {
                    choice_id: "17",
                    title: "월리권 #17",
                    description: "Draw one more time.",
                    value: { deck_index: 17 },
                    secondary: false,
                  },
                ],
                public_context: { reward_count: 1 },
                behavior: { normalized_request_type: "specific_trick_reward", single_surface: false, auto_continue: false },
                surface: {
                  kind: "specific_trick_reward",
                  blocks_public_events: true,
                  specific_trick_reward: {
                    reward_count: 1,
                    options: [{ choice_id: "17", deck_index: 17, name: "월리권 #17", description: "Draw one more time." }],
                  },
                },
              },
            },
          },
        },
      },
    ];
    const pabalMessages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          view_state: {
            prompt: {
              active: {
                request_id: "req_pabal",
                request_type: "pabal_dice_mode",
                player_id: 1,
                timeout_ms: 30000,
                choices: [
                  {
                    choice_id: "plus_one",
                    title: "Roll three dice",
                    description: "Use the default three-die roll this turn.",
                    value: { dice_mode: "plus_one" },
                    secondary: false,
                  },
                  {
                    choice_id: "minus_one",
                    title: "Roll one die",
                    description: "Reduce the roll to one die this turn.",
                    value: { dice_mode: "minus_one" },
                    secondary: false,
                  },
                ],
                public_context: {},
                behavior: { normalized_request_type: "pabal_dice_mode", single_surface: false, auto_continue: false },
                surface: {
                  kind: "pabal_dice_mode",
                  blocks_public_events: true,
                  pabal_dice_mode: {
                    options: [
                      {
                        choice_id: "plus_one",
                        dice_mode: "plus_one",
                        title: "Roll three dice",
                        description: "Use the default three-die roll this turn.",
                      },
                      {
                        choice_id: "minus_one",
                        dice_mode: "minus_one",
                        title: "Roll one die",
                        description: "Reduce the roll to one die this turn.",
                      },
                    ],
                  },
                },
              },
            },
          },
        },
      },
    ];

    expect(selectActivePrompt(rewardMessages)?.surface.specificTrickReward).toEqual({
      rewardCount: 1,
      options: [{ choiceId: "17", deckIndex: 17, name: "월리권 #17", description: "Draw one more time." }],
    });
    expect(selectActivePrompt(pabalMessages)?.surface.pabalDiceMode).toEqual({
      options: [
        {
          choiceId: "plus_one",
          diceMode: "plus_one",
          title: "Roll three dice",
          description: "Use the default three-die roll this turn.",
        },
        {
          choiceId: "minus_one",
          diceMode: "minus_one",
          title: "Roll one die",
          description: "Reduce the roll to one die this turn.",
        },
      ],
    });
  });

  it("falls back to the latest persisted tray for the same player when another player owns the active prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 40,
        session_id: "s1",
        payload: {
          request_id: "req_burden_1",
          request_type: "burden_exchange",
          player_id: 1,
          timeout_ms: 30000,
          public_context: {
            burden_cards: [
              {
                deck_index: 91,
                name: "무거운 짐",
                card_description: "이동 -1",
                burden_cost: 4,
                is_current_target: true,
              },
            ],
          },
        },
      },
      {
        type: "prompt",
        seq: 41,
        session_id: "s1",
        payload: {
          request_id: "req_other_1",
          request_type: "purchase_tile",
          player_id: 2,
          timeout_ms: 30000,
          public_context: {
            tile_index: 8,
          },
        },
      },
    ];

    expect(selectCurrentHandTrayCards(messages, "ko", 1)).toEqual([
      {
        key: "91-무거운 짐",
        title: "무거운 짐",
        effect: "이동 -1 / 제거 비용 4",
        serial: "#91",
        hidden: false,
        currentTarget: true,
      },
    ]);
  });
});
