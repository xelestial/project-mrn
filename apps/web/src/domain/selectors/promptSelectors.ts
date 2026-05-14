import type { InboundMessage, ProtocolPlayerId } from "../../core/contracts/stream";

export type PromptChoiceViewModel = {
  choiceId: string;
  title: string;
  description: string;
  value: Record<string, unknown> | null;
  secondary: boolean;
};

export type PromptContinuationViewModel = {
  promptInstanceId: number | null;
  publicPromptInstanceId?: string | null;
  promptFingerprint: string | null;
  promptFingerprintVersion: string | null;
  resumeToken: string | null;
  frameId: string | null;
  moduleId: string | null;
  moduleType: string | null;
  moduleCursor: string | null;
  batchId: string | null;
  missingPlayerIds?: number[];
  resumeTokensByPlayerId?: Record<string, string>;
  missingPublicPlayerIds?: string[];
  resumeTokensByPublicPlayerId?: Record<string, string>;
  missingSeatIds?: string[];
  resumeTokensBySeatId?: Record<string, string>;
  missingViewerIds?: string[];
  resumeTokensByViewerId?: Record<string, string>;
};

export type PromptEffectContextViewModel = {
  label: string;
  detail: string;
  attribution: string | null;
  tone: "move" | "effect" | "economy";
  source: string;
  intent: string;
  enhanced: boolean;
  sourcePlayerId: number | null;
  sourceFamily: string;
  sourceName: string;
  resourceDelta: Record<string, unknown> | null;
};

export type PromptIdentitySource = "public" | "protocol" | "legacy";

export type PromptIdentityViewModel = {
  primaryPlayerId: ProtocolPlayerId;
  primaryPlayerIdSource: PromptIdentitySource;
  protocolPlayerId: ProtocolPlayerId;
  legacyPlayerId: number | null;
  publicPlayerId: string | null;
  seatId: string | null;
  viewerId: string | null;
};

export type PromptViewModel = {
  requestId: string;
  requestType: string;
  playerId: number;
  identity: PromptIdentityViewModel;
  protocolPlayerId?: ProtocolPlayerId;
  legacyPlayerId?: number | null;
  publicPlayerId?: string | null;
  seatId?: string | null;
  viewerId?: string | null;
  timeoutMs: number;
  choices: PromptChoiceViewModel[];
  publicContext: Record<string, unknown>;
  continuation: PromptContinuationViewModel;
  effectContext: PromptEffectContextViewModel | null;
  behavior: {
    normalizedRequestType: string;
    singleSurface: boolean;
    autoContinue: boolean;
    chainKey: string | null;
    chainItemCount: number | null;
    currentItemDeckIndex: number | null;
  };
  surface: {
    kind: string;
    blocksPublicEvents: boolean;
    movement: {
      rollChoiceId: string | null;
      cardPool: number[];
      canUseTwoCards: boolean;
      cardChoices: Array<{
        choiceId: string;
        cards: number[];
        title: string;
        description: string;
      }>;
    } | null;
    lapReward: {
      budget: number;
      cashPool: number;
      shardsPool: number;
      coinsPool: number;
      cashPointCost: number;
      shardsPointCost: number;
      coinsPointCost: number;
      options: Array<{
        choiceId: string;
        cashUnits: number;
        shardUnits: number;
        coinUnits: number;
        spentPoints: number;
      }>;
    } | null;
    burdenExchangeBatch: {
      burdenCardCount: number;
      currentFValue: number | null;
      supplyThreshold: number | null;
      cards: Array<{
        deckIndex: number | null;
        name: string;
        description: string;
        burdenCost: number | null;
        isCurrentTarget: boolean;
      }>;
    } | null;
    markTarget: {
      actorName: string;
      noneChoiceId: string | null;
      candidates: Array<{
        choiceId: string;
        targetCharacter: string;
        targetCardNo: number | null;
        targetPlayerId: number | null;
      }>;
    } | null;
    characterPick: {
      phase: string;
      draftPhase: number | null;
      draftPhaseLabel: string | null;
      choiceCount: number;
      options: Array<{
        choiceId: string;
        name: string;
        description: string;
        inactiveName?: string;
      }>;
    } | null;
    handChoice: {
      mode: string;
      passChoiceId: string | null;
      cards: Array<{
        choiceId: string | null;
        deckIndex: number | null;
        name: string;
        description: string;
        isHidden: boolean;
        isUsable: boolean;
      }>;
    } | null;
    purchaseTile: {
      tileIndex: number | null;
      cost: number | null;
      yesChoiceId: string | null;
      noChoiceId: string | null;
    } | null;
    trickTileTarget: {
      cardName: string;
      targetScope: string;
      candidateTiles: number[];
      options: Array<{
        choiceId: string;
        tileIndex: number;
        title: string;
        description: string;
      }>;
    } | null;
    coinPlacement: {
      ownedTileCount: number;
      options: Array<{
        choiceId: string;
        tileIndex: number;
        title: string;
        description: string;
      }>;
    } | null;
    doctrineRelief: {
      candidateCount: number;
      options: Array<{
        choiceId: string;
        targetPlayerId: number | null;
        burdenCount: number | null;
        title: string;
        description: string;
      }>;
    } | null;
    geoBonus: {
      actorName: string;
      options: Array<{
        choiceId: string;
        rewardKind: string;
        title: string;
        description: string;
      }>;
    } | null;
    specificTrickReward: {
      rewardCount: number;
      options: Array<{
        choiceId: string;
        deckIndex: number | null;
        name: string;
        description: string;
      }>;
    } | null;
    pabalDiceMode: {
      options: Array<{
        choiceId: string;
        diceMode: string;
        title: string;
        description: string;
      }>;
    } | null;
    runawayStep: {
      bonusChoiceId: string | null;
      stayChoiceId: string | null;
      oneShortPos: number | null;
      bonusTargetPos: number | null;
      bonusTargetKind: string;
    } | null;
    activeFlip: {
      finishChoiceId: string | null;
      options: Array<{
        choiceId: string;
        cardIndex: number | null;
        currentName: string;
        flippedName: string;
      }>;
    } | null;
  };
};

export type HandTrayCardViewModel = {
  key: string;
  title: string;
  effect: string;
  serial: string;
  hidden: boolean;
  currentTarget: boolean;
};

export type DecisionAckViewModel = {
  status: "accepted" | "rejected" | "stale";
  reason: string;
};

export type PromptInteractionFeedbackViewModel =
  | { kind: "none" }
  | { kind: "manual"; message: string }
  | { kind: "rejected" | "stale"; reason: string }
  | { kind: "timed_out" }
  | { kind: "connection_lost" };

export type PromptInteractionViewModel = {
  requestId: string;
  busy: boolean;
  secondsLeft: number | null;
  feedback: PromptInteractionFeedbackViewModel;
  shouldReleaseSubmission: boolean;
};

function latestBackendViewStateEntry(messages: InboundMessage[]): { index: number; viewState: Record<string, unknown> } | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type !== "view_commit") {
      continue;
    }
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    if (viewState) {
      return { index: i, viewState };
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function stringOrEmpty(value: unknown): string {
  return typeof value === "string" && value.trim() ? String(value) : "";
}

function isSecondaryChoiceRecord(choiceId: string, item: Record<string, unknown>): boolean {
  const explicitSecondary = item["secondary"];
  const priority = item["priority"];
  return (
    explicitSecondary === true ||
    priority === "secondary" ||
    priority === "passive" ||
    choiceId === "none" ||
    choiceId === "no"
  );
}

function choiceValueRecord(item: Record<string, unknown>): Record<string, unknown> | null {
  return isRecord(item["value"]) ? { ...item["value"] } : null;
}

function choiceIdFromRecord(item: Record<string, unknown>): string {
  return stringOrEmpty(item["choice_id"] ?? item["choiceId"] ?? item["id"]);
}

function choiceDescriptionText(item: Record<string, unknown>, value: Record<string, unknown> | null): string {
  const explicitDescription = stringOrEmpty(item["description"]);
  if (explicitDescription) {
    return explicitDescription;
  }
  const cardDescription = stringOrEmpty(value?.["card_description"]);
  if (cardDescription) {
    return cardDescription;
  }
  return stringOrEmpty(value?.["description"]);
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function protocolPlayerIdOrNull(value: unknown): ProtocolPlayerId | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return null;
}

export function promptIdentityFromActivePromptPayload(active: Record<string, unknown>): PromptIdentityViewModel | null {
  const protocolPlayerId = protocolPlayerIdOrNull(active["player_id"]);
  const legacyPlayerId = numberOrNull(active["legacy_player_id"]) ?? numberOrNull(active["player_id"]);
  const publicPlayerId = stringOrEmpty(active["public_player_id"]) || null;
  const seatId = stringOrEmpty(active["seat_id"]) || null;
  const viewerId = stringOrEmpty(active["viewer_id"]) || null;
  const primaryPlayerId = publicPlayerId ?? protocolPlayerId ?? legacyPlayerId;
  if (primaryPlayerId === null) {
    return null;
  }
  const primaryPlayerIdSource: PromptIdentitySource =
    publicPlayerId !== null ? "public" : typeof protocolPlayerId === "string" ? "protocol" : "legacy";
  return {
    primaryPlayerId,
    primaryPlayerIdSource,
    protocolPlayerId: protocolPlayerId ?? primaryPlayerId,
    legacyPlayerId,
    publicPlayerId,
    seatId,
    viewerId,
  };
}

export function promptPrimaryTargetId(prompt: PromptViewModel | null): ProtocolPlayerId | null {
  return prompt?.identity.primaryPlayerId ?? null;
}

export function isPromptPrimaryTarget(prompt: PromptViewModel | null, targetId: ProtocolPlayerId | null): boolean {
  return promptPrimaryTargetId(prompt) === targetId;
}

export function isPromptTargetedToLegacyPlayer(prompt: PromptViewModel | null, legacyPlayerId: number | null): boolean {
  return (
    prompt !== null &&
    typeof legacyPlayerId === "number" &&
    Number.isFinite(legacyPlayerId) &&
    prompt.identity.legacyPlayerId === Math.floor(legacyPlayerId)
  );
}

function stringArrayOrNull(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const items = value.map((item) => stringOrEmpty(item)).filter((item) => item.length > 0);
  return items.length > 0 ? items : null;
}

function stringRecordOrNull(value: unknown): Record<string, string> | null {
  if (!isRecord(value)) {
    return null;
  }
  const entries = Object.entries(value)
    .map(([key, token]) => [String(key), stringOrEmpty(token)] as const)
    .filter(([, token]) => token.length > 0);
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function parsePromptEffectContext(raw: unknown): PromptEffectContextViewModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  const label = stringOrEmpty(raw["label"]) || stringOrEmpty(raw["source_name"]);
  const detail = stringOrEmpty(raw["detail"]) || label;
  if (!label && !detail) {
    return null;
  }
  const rawTone = stringOrEmpty(raw["tone"]);
  const tone = rawTone === "move" || rawTone === "effect" || rawTone === "economy" ? rawTone : "effect";
  return {
    label: label || detail,
    detail: detail || label,
    attribution: stringOrEmpty(raw["attribution"]) || null,
    tone,
    source: stringOrEmpty(raw["source"]) || stringOrEmpty(raw["source_family"]) || "system",
    intent: stringOrEmpty(raw["intent"]) || "neutral",
    enhanced: raw["enhanced"] === true,
    sourcePlayerId: numberOrNull(raw["source_player_id"]),
    sourceFamily: stringOrEmpty(raw["source_family"]),
    sourceName: stringOrEmpty(raw["source_name"]),
    resourceDelta: isRecord(raw["resource_delta"]) ? { ...raw["resource_delta"] } : null,
  };
}

function parseChoices(raw: unknown): PromptChoiceViewModel[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => {
      if (!isRecord(item)) {
        return null;
      }
      const choiceId = choiceIdFromRecord(item);
      if (!choiceId) {
        return null;
      }
      const value = choiceValueRecord(item);
      const title = stringOrEmpty(item["title"] ?? item["label"]) || choiceId;
      return {
        choiceId,
        title,
        description: choiceDescriptionText(item, value),
        value,
        secondary: isSecondaryChoiceRecord(choiceId, item),
      };
    })
    .filter((item): item is PromptChoiceViewModel => item !== null);
}

function parsePromptBehavior(raw: unknown, requestType: string, publicContext: Record<string, unknown>) {
  const behavior = isRecord(raw) ? raw : null;
  return {
    normalizedRequestType:
      typeof behavior?.["normalized_request_type"] === "string" && behavior["normalized_request_type"].trim()
        ? behavior["normalized_request_type"]
        : requestType,
    singleSurface: behavior?.["single_surface"] === true,
    autoContinue: behavior?.["auto_continue"] === true,
    chainKey:
      typeof behavior?.["chain_key"] === "string" && behavior["chain_key"].trim() ? behavior["chain_key"] : null,
    chainItemCount: typeof behavior?.["chain_item_count"] === "number" ? behavior["chain_item_count"] : null,
    currentItemDeckIndex:
      typeof behavior?.["current_item_deck_index"] === "number"
        ? behavior["current_item_deck_index"]
        : typeof publicContext["card_deck_index"] === "number"
          ? publicContext["card_deck_index"]
          : null,
  };
}

function parsePromptContinuation(raw: Record<string, unknown>): PromptContinuationViewModel {
  const missingPlayerIds = Array.isArray(raw["missing_player_ids"])
    ? raw["missing_player_ids"].map((item) => numberOrNull(item)).filter((item): item is number => item !== null)
    : null;
  const rawResumeTokens = isRecord(raw["resume_tokens_by_player_id"]) ? raw["resume_tokens_by_player_id"] : null;
  const resumeTokensByPlayerId = rawResumeTokens
    ? Object.fromEntries(
        Object.entries(rawResumeTokens)
          .map(([playerId, token]) => [String(playerId), stringOrEmpty(token)] as const)
          .filter(([, token]) => token.length > 0),
      )
    : null;
  const missingPublicPlayerIds = stringArrayOrNull(raw["missing_public_player_ids"]);
  const resumeTokensByPublicPlayerId = stringRecordOrNull(raw["resume_tokens_by_public_player_id"]);
  const missingSeatIds = stringArrayOrNull(raw["missing_seat_ids"]);
  const resumeTokensBySeatId = stringRecordOrNull(raw["resume_tokens_by_seat_id"]);
  const missingViewerIds = stringArrayOrNull(raw["missing_viewer_ids"]);
  const resumeTokensByViewerId = stringRecordOrNull(raw["resume_tokens_by_viewer_id"]);
  return {
    promptInstanceId: numberOrNull(raw["prompt_instance_id"]),
    publicPromptInstanceId: stringOrEmpty(raw["public_prompt_instance_id"]) || null,
    promptFingerprint: stringOrEmpty(raw["prompt_fingerprint"]) || null,
    promptFingerprintVersion: stringOrEmpty(raw["prompt_fingerprint_version"]) || null,
    resumeToken: stringOrEmpty(raw["resume_token"]) || null,
    frameId: stringOrEmpty(raw["frame_id"]) || null,
    moduleId: stringOrEmpty(raw["module_id"]) || null,
    moduleType: stringOrEmpty(raw["module_type"]) || null,
    moduleCursor: stringOrEmpty(raw["module_cursor"]) || null,
    batchId: stringOrEmpty(raw["batch_id"]) || null,
    ...(missingPlayerIds ? { missingPlayerIds } : {}),
    ...(resumeTokensByPlayerId ? { resumeTokensByPlayerId } : {}),
    ...(missingPublicPlayerIds ? { missingPublicPlayerIds } : {}),
    ...(resumeTokensByPublicPlayerId ? { resumeTokensByPublicPlayerId } : {}),
    ...(missingSeatIds ? { missingSeatIds } : {}),
    ...(resumeTokensBySeatId ? { resumeTokensBySeatId } : {}),
    ...(missingViewerIds ? { missingViewerIds } : {}),
    ...(resumeTokensByViewerId ? { resumeTokensByViewerId } : {}),
  };
}

const REQUIRED_MODULE_CONTINUATION_FIELDS = [
  "resume_token",
  "frame_id",
  "module_id",
  "module_type",
  "module_cursor",
] as const;

function declaresModuleContinuation(raw: Record<string, unknown>): boolean {
  const runnerKind = stringOrEmpty(raw["runner_kind"] ?? raw["runtime_runner_kind"]);
  if (runnerKind === "module") {
    return true;
  }
  return REQUIRED_MODULE_CONTINUATION_FIELDS.some((field) => stringOrEmpty(raw[field]).length > 0);
}

function hasCompleteModuleContinuation(raw: Record<string, unknown>): boolean {
  if (!REQUIRED_MODULE_CONTINUATION_FIELDS.every((field) => stringOrEmpty(raw[field]).length > 0)) {
    return false;
  }
  const moduleType = stringOrEmpty(raw["module_type"]);
  const requestType = stringOrEmpty(raw["request_type"]);
  const moduleCursor = stringOrEmpty(raw["module_cursor"]);
  const isBatchPrompt =
    moduleType === "SimultaneousPromptBatchModule" ||
    (moduleType === "ResupplyModule" &&
      (requestType === "burden_exchange" || requestType === "resupply_choice") &&
      moduleCursor.startsWith("await_resupply_batch"));
  if (!isBatchPrompt) {
    return true;
  }
  return (
    stringOrEmpty(raw["batch_id"]).length > 0 &&
    Array.isArray(raw["missing_player_ids"]) &&
    isRecord(raw["resume_tokens_by_player_id"])
  );
}

function parsePromptSurface(raw: unknown, requestType: string, publicContext: Record<string, unknown>, choicesRaw: unknown) {
  const surface = isRecord(raw) ? raw : null;
  const movement = isRecord(surface?.["movement"]) ? surface?.["movement"] : null;
  const lapReward = isRecord(surface?.["lap_reward"]) ? surface?.["lap_reward"] : null;
  const burdenExchange = isRecord(surface?.["burden_exchange_batch"]) ? surface?.["burden_exchange_batch"] : null;
  const markTarget = isRecord(surface?.["mark_target"]) ? surface?.["mark_target"] : null;
  const characterPick = isRecord(surface?.["character_pick"]) ? surface?.["character_pick"] : null;
  const handChoice = isRecord(surface?.["hand_choice"]) ? surface?.["hand_choice"] : null;
  const purchaseTile = isRecord(surface?.["purchase_tile"]) ? surface?.["purchase_tile"] : null;
  const trickTileTarget = isRecord(surface?.["trick_tile_target"]) ? surface?.["trick_tile_target"] : null;
  const coinPlacement = isRecord(surface?.["coin_placement"]) ? surface?.["coin_placement"] : null;
  const doctrineRelief = isRecord(surface?.["doctrine_relief"]) ? surface?.["doctrine_relief"] : null;
  const geoBonus = isRecord(surface?.["geo_bonus"]) ? surface?.["geo_bonus"] : null;
  const specificTrickReward = isRecord(surface?.["specific_trick_reward"]) ? surface?.["specific_trick_reward"] : null;
  const pabalDiceMode = isRecord(surface?.["pabal_dice_mode"]) ? surface?.["pabal_dice_mode"] : null;
  const runawayStep = isRecord(surface?.["runaway_step"]) ? surface?.["runaway_step"] : null;
  const activeFlip = isRecord(surface?.["active_flip"]) ? surface?.["active_flip"] : null;
  return {
    kind: stringOrEmpty(surface?.["kind"]) || requestType,
    blocksPublicEvents: surface?.["blocks_public_events"] === true || !surface,
    movement:
      movement
        ? {
            rollChoiceId: stringOrEmpty(movement["roll_choice_id"]) || null,
            cardPool: Array.isArray(movement["card_pool"])
              ? movement["card_pool"].map((item) => numberOrNull(item)).filter((item): item is number => item !== null)
              : [],
            canUseTwoCards: movement["can_use_two_cards"] === true,
            cardChoices: Array.isArray(movement["card_choices"])
              ? movement["card_choices"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    cards: Array.isArray(item["cards"])
                      ? item["cards"].map((entry) => numberOrNull(entry)).filter((entry): entry is number => entry !== null)
                      : [],
                    title: stringOrEmpty(item["title"]) || choiceId,
                    description: stringOrEmpty(item["description"]),
                  }];
                })
              : [],
          }
        : null,
    lapReward:
      lapReward &&
      typeof lapReward["budget"] === "number" &&
      typeof lapReward["cash_pool"] === "number" &&
      typeof lapReward["shards_pool"] === "number" &&
      typeof lapReward["coins_pool"] === "number" &&
      typeof lapReward["cash_point_cost"] === "number" &&
      typeof lapReward["shards_point_cost"] === "number" &&
      typeof lapReward["coins_point_cost"] === "number"
        ? {
            budget: lapReward["budget"],
            cashPool: lapReward["cash_pool"],
            shardsPool: lapReward["shards_pool"],
            coinsPool: lapReward["coins_pool"],
            cashPointCost: lapReward["cash_point_cost"],
            shardsPointCost: lapReward["shards_point_cost"],
            coinsPointCost: lapReward["coins_point_cost"],
            options: Array.isArray(lapReward["options"])
              ? lapReward["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  const cashUnits = numberOrNull(item["cash_units"]);
                  const shardUnits = numberOrNull(item["shard_units"]);
                  const coinUnits = numberOrNull(item["coin_units"]);
                  const spentPoints = numberOrNull(item["spent_points"]);
                  if (!choiceId || cashUnits === null || shardUnits === null || coinUnits === null || spentPoints === null) {
                    return [];
                  }
                  return [{ choiceId, cashUnits, shardUnits, coinUnits, spentPoints }];
                })
              : [],
          }
        : null,
    burdenExchangeBatch:
      burdenExchange
        ? {
            burdenCardCount: numberOrNull(burdenExchange["burden_card_count"]) ?? 0,
            currentFValue: numberOrNull(burdenExchange["current_f_value"]),
            supplyThreshold: numberOrNull(burdenExchange["supply_threshold"]),
            cards: Array.isArray(burdenExchange["cards"])
              ? burdenExchange["cards"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  return [
                    {
                      deckIndex: numberOrNull(item["deck_index"]),
                      name: stringOrEmpty(item["name"]) || "Burden",
                      description: stringOrEmpty(item["description"]),
                      burdenCost: numberOrNull(item["burden_cost"]),
                      isCurrentTarget: item["is_current_target"] === true,
                    },
                  ];
                })
              : [],
          }
        : null,
    markTarget:
      markTarget
        ? {
            actorName: stringOrEmpty(markTarget["actor_name"]),
            noneChoiceId: stringOrEmpty(markTarget["none_choice_id"]) || null,
            candidates: Array.isArray(markTarget["candidates"])
              ? markTarget["candidates"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  const targetCharacter = stringOrEmpty(item["target_character"]);
                  if (!choiceId || !targetCharacter) {
                    return [];
                  }
                  return [{
                    choiceId,
                    targetCharacter,
                    targetCardNo: numberOrNull(item["target_card_no"]),
                    targetPlayerId: numberOrNull(item["target_player_id"]),
                  }];
                })
              : [],
          }
        : null,
    characterPick:
      characterPick
        ? {
            phase: stringOrEmpty(characterPick["phase"]) || (requestType === "draft_card" ? "draft" : "final"),
            draftPhase: numberOrNull(characterPick["draft_phase"]),
            draftPhaseLabel: stringOrEmpty(characterPick["draft_phase_label"]) || null,
            choiceCount:
              numberOrNull(characterPick["choice_count"]) ??
              (Array.isArray(characterPick["options"]) ? characterPick["options"].length : 0),
            options: Array.isArray(characterPick["options"])
              ? characterPick["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  const name = stringOrEmpty(item["name"] ?? item["title"] ?? item["label"]);
                  if (!choiceId || !name) {
                    return [];
                  }
                  const inactiveName = stringOrEmpty(item["inactive_name"]);
                  return [
                    {
                      choiceId,
                      name,
                      description: stringOrEmpty(item["description"]),
                      ...(inactiveName ? { inactiveName } : {}),
                    },
                  ];
                })
              : [],
          }
        : null,
    handChoice:
      handChoice
        ? {
            mode: stringOrEmpty(handChoice["mode"]),
            passChoiceId: stringOrEmpty(handChoice["pass_choice_id"]) || null,
            cards: Array.isArray(handChoice["cards"])
              ? handChoice["cards"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  return [{
                    choiceId: choiceIdFromRecord(item) || null,
                    deckIndex: numberOrNull(item["deck_index"]),
                    name: stringOrEmpty(item["name"]) || "Trick",
                    description: stringOrEmpty(item["description"]),
                    isHidden: item["is_hidden"] === true,
                    isUsable: item["is_usable"] === true,
                  }];
                })
              : [],
          }
        : null,
    purchaseTile:
      purchaseTile
        ? {
            tileIndex: numberOrNull(purchaseTile["tile_index"]),
            cost: numberOrNull(purchaseTile["cost"]),
            yesChoiceId: stringOrEmpty(purchaseTile["yes_choice_id"]) || null,
            noChoiceId: stringOrEmpty(purchaseTile["no_choice_id"]) || null,
          }
        : null,
    trickTileTarget:
      trickTileTarget
        ? {
            cardName: stringOrEmpty(trickTileTarget["card_name"]),
            targetScope: stringOrEmpty(trickTileTarget["target_scope"]),
            candidateTiles: Array.isArray(trickTileTarget["candidate_tiles"])
              ? trickTileTarget["candidate_tiles"].map((item) => numberOrNull(item)).filter((item): item is number => item !== null)
              : [],
            options: Array.isArray(trickTileTarget["options"])
              ? trickTileTarget["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  const tileIndex = numberOrNull(item["tile_index"]);
                  if (!choiceId || tileIndex === null) {
                    return [];
                  }
                  return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"]) || choiceId, description: stringOrEmpty(item["description"]) }];
                })
              : [],
          }
        : null,
    coinPlacement:
      coinPlacement
        ? {
            ownedTileCount: numberOrNull(coinPlacement["owned_tile_count"]) ?? 0,
            options: Array.isArray(coinPlacement["options"])
              ? coinPlacement["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  const tileIndex = numberOrNull(item["tile_index"]);
                  if (!choiceId || tileIndex === null) {
                    return [];
                  }
                  return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"]) || choiceId, description: stringOrEmpty(item["description"]) }];
                })
              : [],
          }
        : null,
    doctrineRelief:
      doctrineRelief
        ? {
            candidateCount: numberOrNull(doctrineRelief["candidate_count"]) ?? 0,
            options: Array.isArray(doctrineRelief["options"])
              ? doctrineRelief["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    targetPlayerId: numberOrNull(item["target_player_id"]),
                    burdenCount: numberOrNull(item["burden_count"]),
                    title: stringOrEmpty(item["title"]) || choiceId,
                    description: stringOrEmpty(item["description"]),
                  }];
                })
              : [],
          }
        : null,
    geoBonus:
      geoBonus
        ? {
            actorName: stringOrEmpty(geoBonus["actor_name"]),
            options: Array.isArray(geoBonus["options"])
              ? geoBonus["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    rewardKind: stringOrEmpty(item["reward_kind"]) || choiceId,
                    title: stringOrEmpty(item["title"]) || choiceId,
                    description: stringOrEmpty(item["description"]),
                  }];
                })
              : [],
          }
        : null,
    specificTrickReward:
      specificTrickReward
        ? {
            rewardCount: numberOrNull(specificTrickReward["reward_count"]) ?? 0,
            options: Array.isArray(specificTrickReward["options"])
              ? specificTrickReward["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    deckIndex: numberOrNull(item["deck_index"]),
                    name: stringOrEmpty(item["name"]) || choiceId,
                    description: stringOrEmpty(item["description"]),
                  }];
                })
              : [],
          }
        : null,
    pabalDiceMode:
      pabalDiceMode
        ? {
            options: Array.isArray(pabalDiceMode["options"])
              ? pabalDiceMode["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    diceMode: stringOrEmpty(item["dice_mode"]) || choiceId,
                    title: stringOrEmpty(item["title"]) || choiceId,
                    description: stringOrEmpty(item["description"]),
                  }];
                })
              : [],
          }
        : null,
    runawayStep:
      runawayStep
        ? {
            bonusChoiceId: stringOrEmpty(runawayStep["bonus_choice_id"]) || null,
            stayChoiceId: stringOrEmpty(runawayStep["stay_choice_id"]) || null,
            oneShortPos: numberOrNull(runawayStep["one_short_pos"]),
            bonusTargetPos: numberOrNull(runawayStep["bonus_target_pos"]),
            bonusTargetKind: stringOrEmpty(runawayStep["bonus_target_kind"]),
          }
        : null,
    activeFlip:
      activeFlip
        ? {
            finishChoiceId: stringOrEmpty(activeFlip["finish_choice_id"]) || null,
            options: Array.isArray(activeFlip["options"])
              ? activeFlip["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = choiceIdFromRecord(item);
                  if (!choiceId) {
                    return [];
                  }
                  return [{
                    choiceId,
                    cardIndex: numberOrNull(item["card_index"]),
                    currentName: stringOrEmpty(item["current_name"]),
                    flippedName: stringOrEmpty(item["flipped_name"]),
                  }];
                })
              : [],
          }
        : null,
  };
}

export function promptViewModelFromActivePromptPayload(active: Record<string, unknown>): PromptViewModel | null {
  if (!active) {
    return null;
  }
  const requestId = active["request_id"];
  const requestType = active["request_type"];
  const identity = promptIdentityFromActivePromptPayload(active);
  const protocolPlayerId = protocolPlayerIdOrNull(active["player_id"]);
  const legacyPlayerId = identity?.legacyPlayerId ?? null;
  if (
    typeof requestId !== "string" ||
    !requestId.trim() ||
    typeof requestType !== "string" ||
    identity === null ||
    protocolPlayerId === null ||
    legacyPlayerId === null
  ) {
    return null;
  }
  if (declaresModuleContinuation(active) && !hasCompleteModuleContinuation(active)) {
    return null;
  }
  const publicContext = isRecord(active["public_context"]) ? active["public_context"] : {};
  const choicesRaw = Array.isArray(active["choices"]) ? active["choices"] : active["legal_choices"];
  return {
    requestId,
    requestType,
    playerId: legacyPlayerId,
    identity,
    protocolPlayerId,
    legacyPlayerId,
    publicPlayerId: identity.publicPlayerId,
    seatId: identity.seatId,
    viewerId: identity.viewerId,
    timeoutMs: typeof active["timeout_ms"] === "number" ? active["timeout_ms"] : 30000,
    choices: parseChoices(choicesRaw),
    publicContext: { ...publicContext },
    continuation: parsePromptContinuation(active),
    effectContext: parsePromptEffectContext(active["effect_context"]),
    behavior: parsePromptBehavior(active["behavior"], requestType, publicContext),
    surface: parsePromptSurface(
      active["surface"],
      requestType,
      publicContext,
      choicesRaw
    ),
  };
}

function selectBackendActivePrompt(messages: InboundMessage[]): PromptViewModel | null {
  const entry = latestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const prompt = isRecord(entry.viewState["prompt"]) ? entry.viewState["prompt"] : null;
  const active = isRecord(prompt?.["active"]) ? prompt["active"] : null;
  if (!active) {
    return null;
  }
  return promptViewModelFromActivePromptPayload(active);
}

export function selectActivePrompt(messages: InboundMessage[]): PromptViewModel | null {
  return selectBackendActivePrompt(messages);
}

export function selectLatestDecisionAck(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  if (!requestId.trim()) {
    return null;
  }
  return selectBackendLatestPromptFeedback(messages, requestId) ?? selectLatestRawDecisionAck(messages, requestId);
}

function selectBackendLatestPromptFeedback(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  const entry = latestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const prompt = isRecord(entry.viewState["prompt"]) ? entry.viewState["prompt"] : null;
  const feedback = isRecord(prompt?.["last_feedback"]) ? prompt["last_feedback"] : null;
  if (!feedback || feedback["request_id"] !== requestId) {
    return null;
  }
  const status = feedback["status"];
  if (status !== "accepted" && status !== "rejected" && status !== "stale") {
    return null;
  }
  return {
    status,
    reason: typeof feedback["reason"] === "string" ? feedback["reason"] : "",
  };
}

function selectLatestRawDecisionAck(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.type !== "decision_ack") {
      continue;
    }
    const payload = message.payload;
    if (payload["request_id"] !== requestId) {
      continue;
    }
    const status = payload["status"];
    if (status !== "accepted" && status !== "rejected" && status !== "stale") {
      continue;
    }
    return {
      status,
      reason: typeof payload["reason"] === "string" ? payload["reason"] : "",
    };
  }
  return null;
}

function selectBackendHandTrayCards(messages: InboundMessage[]): HandTrayCardViewModel[] | null {
  const entry = latestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const handTray = isRecord(entry.viewState["hand_tray"]) ? entry.viewState["hand_tray"] : null;
  const cards = Array.isArray(handTray?.["items"])
    ? handTray["items"]
    : Array.isArray(handTray?.["cards"])
      ? handTray["cards"]
      : null;
  if (!cards) {
    return null;
  }
  return cards.flatMap((item, index) => {
    if (!isRecord(item)) {
      return [];
    }
    const deckIndex = typeof item["deck_index"] === "number" ? item["deck_index"] : null;
    const title = stringOrEmpty(item["title"]) || stringOrEmpty(item["name"]) || "Card";
    return [
      {
        key: stringOrEmpty(item["key"]) || `${deckIndex ?? index}-${title}`,
        title,
        effect: stringOrEmpty(item["effect"]) || stringOrEmpty(item["description"]),
        serial: stringOrEmpty(item["serial"]),
        hidden: item["is_hidden"] === true || item["hidden"] === true,
        currentTarget: item["is_current_target"] === true || item["currentTarget"] === true,
      },
    ];
  });
}

export function selectCurrentHandTrayCards(
  messages: InboundMessage[],
  locale: string,
  preferredPlayerId: number | null
): HandTrayCardViewModel[] {
  void locale;
  void preferredPlayerId;
  const backendHandTray = selectBackendHandTrayCards(messages);
  if (backendHandTray) {
    return backendHandTray;
  }
  return [];
}

type SelectPromptInteractionArgs = {
  messages: InboundMessage[];
  activePrompt: PromptViewModel | null;
  trackedRequestId: string;
  submitting: boolean;
  expiresAtMs: number | null;
  nowMs: number;
  streamStatus: string;
  manualFeedbackMessage?: string;
};

export function selectPromptInteractionState({
  messages,
  activePrompt,
  trackedRequestId,
  submitting,
  expiresAtMs,
  nowMs,
  streamStatus,
  manualFeedbackMessage = "",
}: SelectPromptInteractionArgs): PromptInteractionViewModel {
  const requestId = (activePrompt?.requestId ?? trackedRequestId).trim();
  const latestAck = requestId ? selectLatestDecisionAck(messages, requestId) : null;
  const secondsLeft =
    expiresAtMs === null ? null : Math.max(0, Math.ceil((expiresAtMs - nowMs) / 1000));
  const disconnected = streamStatus !== "connected" && streamStatus !== "connecting";
  const promptSwapped =
    Boolean(submitting && trackedRequestId.trim()) &&
    activePrompt !== null &&
    activePrompt.requestId !== trackedRequestId.trim();
  const promptSettled = latestAck !== null || disconnected || promptSwapped || (submitting && activePrompt === null);
  const shouldReleaseSubmission = submitting && promptSettled;

  let feedback: PromptInteractionFeedbackViewModel = { kind: "none" };
  if (manualFeedbackMessage.trim()) {
    feedback = { kind: "manual", message: manualFeedbackMessage.trim() };
  } else if (latestAck?.status === "rejected" || latestAck?.status === "stale") {
    feedback = { kind: latestAck.status, reason: latestAck.reason };
  } else if (submitting && disconnected) {
    feedback = { kind: "connection_lost" };
  } else if (activePrompt !== null && !submitting && secondsLeft === 0) {
    feedback = { kind: "timed_out" };
  }

  return {
    requestId,
    busy: submitting && !shouldReleaseSubmission,
    secondsLeft,
    feedback,
    shouldReleaseSubmission,
  };
}
