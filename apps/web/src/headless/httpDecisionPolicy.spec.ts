import { afterEach, describe, expect, it, vi } from "vitest";
import type { HeadlessDecisionContext } from "./HeadlessGameClient";
import { buildHttpDecisionPolicyRequest, createHttpDecisionPolicy } from "./httpDecisionPolicy";

function context(): HeadlessDecisionContext {
  return {
    sessionId: "sess_http_policy",
    playerId: 2,
    identity: {
      primaryPlayerId: "player_public_2",
      primaryPlayerIdSource: "public",
      protocolPlayerId: "player_public_2",
      legacyPlayerId: 2,
      publicPlayerId: "player_public_2",
      seatId: "seat_public_2",
      viewerId: "viewer_public_2",
    },
    lastCommitSeq: 42,
    messages: [],
    latestCommit: {
      schema_version: 1,
      commit_seq: 42,
      source_event_seq: 100,
      round_index: 3,
      turn_index: 8,
      turn_label: "R3-T8",
      viewer: { role: "seat", player_id: 2, seat: 2 },
      runtime: {
        status: "waiting_input",
        round_index: 3,
        turn_index: 8,
        turn_label: "R3-T8",
        active_frame_id: "frame:2",
        active_module_id: "module:2",
        active_module_type: "PurchaseTileModule",
        module_path: ["frame:2", "module:2"],
      },
      view_state: {
        players: {
          items: [
            { player_id: 1, cash: 17, score: 4, total_score: 4, shards: 2, owned_tile_count: 3, alive: true },
            {
              player_id: 2,
              legacy_player_id: 2,
              public_player_id: "player_public_2",
              seat_id: "seat_public_2",
              viewer_id: "viewer_public_2",
              cash: 24,
              score: 5,
              total_score: 5,
              shards: 3,
              owned_tile_count: 4,
              position: 12,
              alive: true,
              current_character_face: "박수",
              hidden_trick_count: 2,
            },
          ],
        },
      },
    },
    prompt: {
      requestId: "req_buy",
      requestType: "purchase_tile",
      playerId: 2,
      protocolPlayerId: "player_public_2",
      legacyPlayerId: 2,
      publicPlayerId: "player_public_2",
      seatId: "seat_public_2",
      viewerId: "viewer_public_2",
      timeoutMs: 30000,
      choices: [
        {
          choiceId: "buy",
          title: "구매",
          description: "타일 구매",
          value: { tile_index: 12, buy: true },
          secondary: false,
        },
        {
          choiceId: "pass",
          title: "넘김",
          description: "",
          value: null,
          secondary: true,
        },
      ],
      publicContext: {},
      continuation: {
        promptInstanceId: 7,
        publicPromptInstanceId: "prompt_public_buy_7",
        promptFingerprint: null,
        promptFingerprintVersion: null,
        resumeToken: "resume:req_buy",
        frameId: "frame:2",
        moduleId: "module:2",
        moduleType: "PurchaseTileModule",
        moduleCursor: "await_choice",
        batchId: null,
      },
      effectContext: null,
      behavior: {
        normalizedRequestType: "purchase_tile",
        singleSurface: false,
        autoContinue: false,
        chainKey: null,
        chainItemCount: null,
        currentItemDeckIndex: null,
      },
      surface: {
        kind: "purchase_tile",
        blocksPublicEvents: false,
        movement: null,
        lapReward: null,
        burdenExchangeBatch: null,
        markTarget: null,
        characterPick: null,
        handChoice: null,
        purchaseTile: { tileIndex: 12, cost: 5, yesChoiceId: "buy", noChoiceId: "pass" },
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
    legalChoices: [],
  };
}

describe("httpDecisionPolicy", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds a compact projected request without raw stream messages", () => {
    const request = buildHttpDecisionPolicyRequest({
      ...context(),
      legalChoices: context().prompt.choices,
    });

    expect(request).toMatchObject({
      protocol_version: 1,
      session_id: "sess_http_policy",
      player_id: 2,
      protocol_player_id: "player_public_2",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
      identity: {
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
      },
      commit_seq: 42,
      runtime: {
        status: "waiting_input",
        round_index: 3,
        turn_index: 8,
        active_module_type: "PurchaseTileModule",
      },
      prompt: {
        request_id: "req_buy",
        request_type: "purchase_tile",
        prompt_instance_id: 7,
        public_prompt_instance_id: "prompt_public_buy_7",
        public_context: {},
      },
      player_summary: {
        player_id: 2,
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
        cash: 24,
        score: 5,
        shards: 3,
        owned_tile_count: 4,
        character: "박수",
      },
    });
    expect(request.legal_choices.map((choice) => choice.choice_id)).toEqual(["buy", "pass"]);
    expect(JSON.stringify(request)).not.toContain("messages");
    expect(JSON.stringify(request)).not.toContain("hidden_trick_count");
  });

  it("keeps numeric-only prompts as explicit legacy policy identity", () => {
    const baseContext = context();
    const request = buildHttpDecisionPolicyRequest({
      ...baseContext,
      prompt: {
        ...baseContext.prompt,
        protocolPlayerId: 2,
        legacyPlayerId: null,
        publicPlayerId: null,
        seatId: null,
        viewerId: null,
      },
      legalChoices: baseContext.prompt.choices,
    });

    expect(request).toMatchObject({
      player_id: 2,
      protocol_player_id: 2,
      legacy_player_id: 2,
      public_player_id: null,
      seat_id: null,
      viewer_id: null,
      identity: {
        primary_player_id: 2,
        primary_player_id_source: "legacy",
        protocol_player_id: 2,
        legacy_player_id: 2,
        public_player_id: null,
        seat_id: null,
        viewer_id: null,
      },
    });
  });

  it("uses the HTTP response as the policy decision", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ choice_id: "pass", choice_payload: { reason: "cash_guard" } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const policy = createHttpDecisionPolicy({ endpoint: "http://127.0.0.1:7777/decide" });

    await expect(policy({ ...context(), legalChoices: context().prompt.choices })).resolves.toEqual({
      choiceId: "pass",
      choicePayload: { reason: "cash_guard" },
    });
  });
});
