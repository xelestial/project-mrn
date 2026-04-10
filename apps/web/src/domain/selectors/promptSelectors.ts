import type { InboundMessage } from "../../core/contracts/stream";

export type PromptChoiceViewModel = {
  choiceId: string;
  title: string;
  description: string;
  value: Record<string, unknown> | null;
  secondary: boolean;
};

export type PromptViewModel = {
  requestId: string;
  requestType: string;
  playerId: number;
  timeoutMs: number;
  choices: PromptChoiceViewModel[];
  publicContext: Record<string, unknown>;
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
      options: Array<{
        choiceId: string;
        name: string;
        description: string;
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

function latestBackendViewState(messages: InboundMessage[]): Record<string, unknown> | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    if (viewState) {
      return viewState;
    }
  }
  return null;
}

function hasAnyBackendViewState(messages: InboundMessage[]): boolean {
  return latestBackendViewState(messages) !== null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function stringOrEmpty(value: unknown): string {
  return typeof value === "string" && value.trim() ? String(value) : "";
}

function isKoreanLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith("ko");
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

function eventPlayerId(payload: Record<string, unknown>): number | null {
  return numberOrNull(payload["player_id"] ?? payload["acting_player_id"] ?? payload["player"]);
}

function closesPromptByPhaseProgress(requestType: string, payload: Record<string, unknown>, promptPlayerId: number): boolean {
  const eventType = stringOrEmpty(payload["event_type"]);
  const payloadPlayerId = eventPlayerId(payload);
  if (requestType === "draft_card") {
    return (
      (eventType === "draft_pick" && payloadPlayerId === promptPlayerId) ||
      eventType === "final_character_choice" ||
      eventType === "turn_start"
    );
  }
  if (requestType === "final_character" || requestType === "final_character_choice") {
    return (eventType === "final_character_choice" && payloadPlayerId === promptPlayerId) || eventType === "turn_start";
  }
  return false;
}

function isPromptClosed(messages: InboundMessage[], promptIndex: number, requestId: string, requestType: string, playerId: number): boolean {
  for (let i = promptIndex + 1; i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type === "decision_ack") {
      if (message.payload["request_id"] !== requestId) {
        continue;
      }
      const status = message.payload["status"];
      if (status === "accepted" || status === "stale") {
        return true;
      }
      continue;
    }
    if (message.type !== "event") {
      continue;
    }
    if (message.payload["request_id"] === requestId) {
      const eventType = message.payload["event_type"];
      if (eventType === "decision_resolved" || eventType === "decision_timeout_fallback") {
        return true;
      }
    }
    if (closesPromptByPhaseProgress(requestType, message.payload, playerId)) {
      return true;
    }
  }
  return false;
}

function handTrayCardsFromPublicContext(publicContext: Record<string, unknown>, locale: string): HandTrayCardViewModel[] {
  const fullHand = Array.isArray(publicContext["full_hand"]) ? publicContext["full_hand"] : [];
  if (fullHand.length > 0) {
    return fullHand.flatMap((item, index) => {
      if (!isRecord(item)) {
        return [];
      }
      const deckIndex = typeof item["deck_index"] === "number" ? item["deck_index"] : null;
      const title = stringOrEmpty(item["name"]) || (isKoreanLocale(locale) ? "잔꾀" : "Trick");
      const effect = stringOrEmpty(item["card_description"]) || (isKoreanLocale(locale) ? "효과 없음" : "No effect text");
      return [
        {
          key: `${deckIndex ?? index}-${title}`,
          title,
          effect,
          serial: deckIndex === null ? "" : `#${deckIndex}`,
          hidden: item["is_hidden"] === true,
          currentTarget: item["is_current_target"] === true,
        },
      ];
    });
  }

  const burdenCards = Array.isArray(publicContext["burden_cards"]) ? publicContext["burden_cards"] : [];
  if (burdenCards.length > 0) {
    return burdenCards.flatMap((item, index) => {
      if (!isRecord(item)) {
        return [];
      }
      const deckIndex = typeof item["deck_index"] === "number" ? item["deck_index"] : null;
      const burdenCost = typeof item["burden_cost"] === "number" ? item["burden_cost"] : null;
      const title = stringOrEmpty(item["name"]) || (isKoreanLocale(locale) ? "짐" : "Burden");
      const effectBase = stringOrEmpty(item["card_description"]) || (isKoreanLocale(locale) ? "효과 없음" : "No effect text");
      const effect =
        burdenCost === null
          ? effectBase
          : isKoreanLocale(locale)
            ? `${effectBase} / 제거 비용 ${burdenCost}`
            : `${effectBase} / remove cost ${burdenCost}`;
      return [
        {
          key: `${deckIndex ?? index}-${title}`,
          title,
          effect,
          serial: deckIndex === null ? "" : `#${deckIndex}`,
          hidden: false,
          currentTarget: item["is_current_target"] === true,
        },
      ];
    });
  }

  return [];
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
      const choiceId = item["choice_id"];
      if (typeof choiceId !== "string" || !choiceId.trim()) {
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "movement"
          ? {
              rollChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && ["dice", "roll"].includes(stringOrEmpty(item["choice_id"])))
                  ? stringOrEmpty(
                      choicesRaw.find((item) => isRecord(item) && ["dice", "roll"].includes(stringOrEmpty(item["choice_id"])))?.["choice_id"]
                    ) || null
                  : null,
              cardPool: Array.isArray(choicesRaw)
                ? Array.from(
                    new Set(
                      choicesRaw.flatMap((item) => {
                        const value = isRecord(item) && isRecord(item["value"]) ? item["value"] : null;
                        return Array.isArray(value?.["card_values"])
                          ? value["card_values"].map((entry) => numberOrNull(entry)).filter((entry): entry is number => entry !== null)
                          : [];
                      })
                    )
                  ).sort((a, b) => a - b)
                : [],
              canUseTwoCards:
                Array.isArray(choicesRaw) &&
                choicesRaw.some((item) => {
                  const value = isRecord(item) && isRecord(item["value"]) ? item["value"] : null;
                  return Array.isArray(value?.["card_values"]) && value["card_values"].length === 2;
                }),
              cardChoices: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    const value = choiceValueRecord(item);
                    const cards = Array.isArray(value?.["card_values"])
                      ? value["card_values"].map((entry) => numberOrNull(entry)).filter((entry): entry is number => entry !== null)
                      : [];
                    if (!choiceId || cards.length === 0) {
                      return [];
                    }
                    return [{ choiceId, cards, title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId, description: choiceDescriptionText(item, value) }];
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "lap_reward"
          ? {
              budget: numberOrNull(publicContext["budget"]) ?? 0,
              cashPool: numberOrNull((isRecord(publicContext["pools"]) ? publicContext["pools"]["cash"] : null)) ?? 0,
              shardsPool: numberOrNull((isRecord(publicContext["pools"]) ? publicContext["pools"]["shards"] : null)) ?? 0,
              coinsPool: numberOrNull((isRecord(publicContext["pools"]) ? publicContext["pools"]["coins"] : null)) ?? 0,
              cashPointCost: numberOrNull(publicContext["cash_point_cost"]) ?? 1,
              shardsPointCost: numberOrNull(publicContext["shards_point_cost"]) ?? 1,
              coinsPointCost: numberOrNull(publicContext["coins_point_cost"]) ?? 1,
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item) || !isRecord(item["value"])) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    const value = item["value"];
                    const cashUnits = numberOrNull(value["cash_units"]);
                    const shardUnits = numberOrNull(value["shard_units"]);
                    const coinUnits = numberOrNull(value["coin_units"]);
                    const spentPoints = numberOrNull(value["spent_points"]);
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
        : requestType === "burden_exchange"
          ? {
              burdenCardCount: numberOrNull(publicContext["burden_card_count"]) ?? 0,
              currentFValue: numberOrNull(publicContext["current_f_value"]),
              supplyThreshold: numberOrNull(publicContext["supply_threshold"]),
              cards: Array.isArray(publicContext["burden_cards"])
                ? publicContext["burden_cards"].flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    return [
                      {
                        deckIndex: numberOrNull(item["deck_index"]),
                        name: stringOrEmpty(item["name"]) || "Burden",
                        description: stringOrEmpty(item["card_description"]),
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "mark_target"
          ? {
              actorName: stringOrEmpty(publicContext["actor_name"]),
              noneChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "none")
                  ? "none"
                  : null,
              candidates: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId || choiceId === "none") {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    const targetCharacter = stringOrEmpty(value?.["target_character"]) || stringOrEmpty(item["title"] ?? item["label"]);
                    if (!targetCharacter) {
                      return [];
                    }
                    return [{
                      choiceId,
                      targetCharacter,
                      targetCardNo: numberOrNull(value?.["target_card_no"]),
                      targetPlayerId: numberOrNull(value?.["target_player_id"]),
                    }];
                  })
                : [],
            }
          : null,
    characterPick:
      characterPick
        ? {
            phase: stringOrEmpty(characterPick["phase"]) || (requestType === "draft_card" ? "draft" : "final"),
            options: Array.isArray(characterPick["options"])
              ? characterPick["options"].flatMap((item) => {
                  if (!isRecord(item)) {
                    return [];
                  }
                  const choiceId = stringOrEmpty(item["choice_id"]);
                  const name = stringOrEmpty(item["name"]);
                  if (!choiceId || !name) {
                    return [];
                  }
                  return [{ choiceId, name, description: stringOrEmpty(item["description"]) }];
                })
              : [],
          }
        : requestType === "draft_card" || requestType === "final_character" || requestType === "final_character_choice"
          ? {
              phase: requestType === "draft_card" ? "draft" : "final",
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    const name = stringOrEmpty(item["title"] ?? item["label"]);
                    if (!choiceId || !name) {
                      return [];
                    }
                    return [{ choiceId, name, description: choiceDescriptionText(item, choiceValueRecord(item)) }];
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
                    choiceId: stringOrEmpty(item["choice_id"]) || null,
                    deckIndex: numberOrNull(item["deck_index"]),
                    name: stringOrEmpty(item["name"]) || "Trick",
                    description: stringOrEmpty(item["description"]),
                    isHidden: item["is_hidden"] === true,
                    isUsable: item["is_usable"] === true,
                  }];
                })
              : [],
          }
        : requestType === "trick_to_use" || requestType === "hidden_trick_card"
          ? {
              mode: requestType === "hidden_trick_card" ? "hidden" : "use",
              passChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "none") ? "none" : null,
              cards: Array.isArray(publicContext["full_hand"])
                ? publicContext["full_hand"].flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const deckIndex = numberOrNull(item["deck_index"]);
                    const linkedChoice =
                      deckIndex !== null && Array.isArray(choicesRaw)
                        ? choicesRaw.find((choice) => isRecord(choice) && numberOrNull(choiceValueRecord(choice)?.["deck_index"]) === deckIndex)
                        : null;
                    return [{
                      choiceId: isRecord(linkedChoice) ? stringOrEmpty(linkedChoice["choice_id"]) || null : null,
                      deckIndex,
                      name: stringOrEmpty(item["name"]) || "Trick",
                      description: stringOrEmpty(item["card_description"]),
                      isHidden: item["is_hidden"] === true,
                      isUsable: item["is_usable"] === true && linkedChoice !== null,
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
        : requestType === "purchase_tile"
          ? {
              tileIndex: numberOrNull(publicContext["tile_index"]),
              cost: numberOrNull(publicContext["cost"] ?? publicContext["tile_purchase_cost"]),
              yesChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "yes")
                  ? "yes"
                  : null,
              noChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "no")
                  ? "no"
                  : null,
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
                  const tileIndex = numberOrNull(item["tile_index"]);
                  if (!choiceId || tileIndex === null) {
                    return [];
                  }
                  return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"]) || choiceId, description: stringOrEmpty(item["description"]) }];
                })
              : [],
          }
        : requestType === "trick_tile_target"
          ? {
              cardName: stringOrEmpty(publicContext["card_name"]),
              targetScope: stringOrEmpty(publicContext["target_scope"]),
              candidateTiles: Array.isArray(publicContext["candidate_tiles"])
                ? publicContext["candidate_tiles"].map((item) => numberOrNull(item)).filter((item): item is number => item !== null)
                : [],
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    const value = choiceValueRecord(item);
                    const tileIndex = numberOrNull(value?.["tile_index"]);
                    if (!choiceId || tileIndex === null) {
                      return [];
                    }
                    return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId, description: choiceDescriptionText(item, value) }];
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
                  const tileIndex = numberOrNull(item["tile_index"]);
                  if (!choiceId || tileIndex === null) {
                    return [];
                  }
                  return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"]) || choiceId, description: stringOrEmpty(item["description"]) }];
                })
              : [],
          }
        : requestType === "coin_placement"
          ? {
              ownedTileCount: numberOrNull(publicContext["owned_tile_count"]) ?? 0,
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    const value = choiceValueRecord(item);
                    const tileIndex = numberOrNull(value?.["tile_index"]);
                    if (!choiceId || tileIndex === null) {
                      return [];
                    }
                    return [{ choiceId, tileIndex, title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId, description: choiceDescriptionText(item, value) }];
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "doctrine_relief"
          ? {
              candidateCount: numberOrNull(publicContext["candidate_count"]) ?? 0,
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId) {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    return [{
                      choiceId,
                      targetPlayerId: numberOrNull(value?.["target_player_id"]),
                      burdenCount: numberOrNull(value?.["burden_count"]),
                      title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId,
                      description: choiceDescriptionText(item, value),
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "geo_bonus"
          ? {
              actorName: stringOrEmpty(publicContext["actor_name"]),
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId) {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    return [{
                      choiceId,
                      rewardKind: stringOrEmpty(value?.["choice"]) || choiceId,
                      title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId,
                      description: choiceDescriptionText(item, value),
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "specific_trick_reward"
          ? {
              rewardCount: numberOrNull(publicContext["reward_count"]) ?? 0,
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId) {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    return [{
                      choiceId,
                      deckIndex: numberOrNull(value?.["deck_index"]),
                      name: stringOrEmpty(item["title"] ?? item["label"]) || choiceId,
                      description: choiceDescriptionText(item, value),
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "pabal_dice_mode"
          ? {
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId) {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    return [{
                      choiceId,
                      diceMode: stringOrEmpty(value?.["dice_mode"]) || choiceId,
                      title: stringOrEmpty(item["title"] ?? item["label"]) || choiceId,
                      description: choiceDescriptionText(item, value),
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
        : requestType === "runaway_step_choice"
          ? {
              bonusChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "yes") ? "yes" : null,
              stayChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "no") ? "no" : null,
              oneShortPos: numberOrNull(publicContext["one_short_pos"]),
              bonusTargetPos: numberOrNull(publicContext["bonus_target_pos"]),
              bonusTargetKind: stringOrEmpty(publicContext["bonus_target_kind"]),
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
                  const choiceId = stringOrEmpty(item["choice_id"]);
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
        : requestType === "active_flip"
          ? {
              finishChoiceId:
                Array.isArray(choicesRaw) && choicesRaw.some((item) => isRecord(item) && stringOrEmpty(item["choice_id"]) === "none")
                  ? "none"
                  : null,
              options: Array.isArray(choicesRaw)
                ? choicesRaw.flatMap((item) => {
                    if (!isRecord(item)) {
                      return [];
                    }
                    const choiceId = stringOrEmpty(item["choice_id"]);
                    if (!choiceId || choiceId === "none") {
                      return [];
                    }
                    const value = choiceValueRecord(item);
                    return [{
                      choiceId,
                      cardIndex: numberOrNull(value?.["card_index"]),
                      currentName: stringOrEmpty(value?.["current_name"]),
                      flippedName: stringOrEmpty(value?.["flipped_name"]),
                    }];
                  })
                : [],
            }
          : null,
  };
}

function selectBackendActivePrompt(messages: InboundMessage[]): PromptViewModel | null {
  const viewState = latestBackendViewState(messages);
  const prompt = isRecord(viewState?.["prompt"]) ? viewState["prompt"] : null;
  const active = isRecord(prompt?.["active"]) ? prompt["active"] : null;
  if (!active) {
    return null;
  }
  const requestId = active["request_id"];
  const requestType = active["request_type"];
  const playerId = active["player_id"];
  if (typeof requestId !== "string" || !requestId.trim() || typeof requestType !== "string" || typeof playerId !== "number") {
    return null;
  }
  return {
    requestId,
    requestType,
    playerId,
    timeoutMs: typeof active["timeout_ms"] === "number" ? active["timeout_ms"] : 30000,
    choices: parseChoices(active["choices"]),
    publicContext: isRecord(active["public_context"]) ? { ...active["public_context"] } : {},
    behavior: parsePromptBehavior(active["behavior"], requestType, isRecord(active["public_context"]) ? active["public_context"] : {}),
    surface: parsePromptSurface(
      active["surface"],
      requestType,
      isRecord(active["public_context"]) ? active["public_context"] : {},
      active["choices"]
    ),
  };
}

export function selectActivePrompt(messages: InboundMessage[]): PromptViewModel | null {
  const backendPrompt = selectBackendActivePrompt(messages);
  if (backendPrompt) {
    return backendPrompt;
  }
  if (hasAnyBackendViewState(messages)) {
    return null;
  }
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const promptMessage = messages[i];
    if (promptMessage.type !== "prompt") {
      continue;
    }
    const requestId = promptMessage.payload["request_id"];
    if (typeof requestId !== "string" || !requestId.trim()) {
      continue;
    }
    const requestType =
      typeof promptMessage.payload["request_type"] === "string" ? String(promptMessage.payload["request_type"]) : "-";
    const playerId = typeof promptMessage.payload["player_id"] === "number" ? promptMessage.payload["player_id"] : 0;
    if (isPromptClosed(messages, i, requestId, requestType, playerId)) {
      continue;
    }
    return {
      requestId,
      requestType,
      playerId,
      timeoutMs: typeof promptMessage.payload["timeout_ms"] === "number" ? promptMessage.payload["timeout_ms"] : 30000,
      choices: parseChoices(promptMessage.payload["legal_choices"]),
      publicContext: isRecord(promptMessage.payload["public_context"]) ? { ...promptMessage.payload["public_context"] } : {},
      behavior: parsePromptBehavior(
        null,
        requestType,
        isRecord(promptMessage.payload["public_context"]) ? promptMessage.payload["public_context"] : {}
      ),
      surface: parsePromptSurface(
        null,
        requestType,
        isRecord(promptMessage.payload["public_context"]) ? promptMessage.payload["public_context"] : {},
        promptMessage.payload["legal_choices"]
      ),
    };
  }
  return null;
}

export function selectLatestDecisionAck(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  if (!requestId.trim()) {
    return null;
  }
  const backendAck = selectBackendLatestPromptFeedback(messages, requestId);
  if (backendAck) {
    return backendAck;
  }
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "decision_ack") {
      continue;
    }
    if (message.payload["request_id"] !== requestId) {
      continue;
    }
    const status = message.payload["status"];
    if (status !== "accepted" && status !== "rejected" && status !== "stale") {
      return null;
    }
    return {
      status,
      reason: typeof message.payload["reason"] === "string" ? message.payload["reason"] : "",
    };
  }
  return null;
}

function selectBackendLatestPromptFeedback(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  const viewState = latestBackendViewState(messages);
  const prompt = isRecord(viewState?.["prompt"]) ? viewState["prompt"] : null;
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

function selectBackendHandTrayCards(messages: InboundMessage[]): HandTrayCardViewModel[] | null {
  const viewState = latestBackendViewState(messages);
  const handTray = isRecord(viewState?.["hand_tray"]) ? viewState["hand_tray"] : null;
  const cards = Array.isArray(handTray?.["cards"]) ? handTray["cards"] : null;
  if (!cards) {
    return null;
  }
  return cards.flatMap((item, index) => {
    if (!isRecord(item)) {
      return [];
    }
    const deckIndex = typeof item["deck_index"] === "number" ? item["deck_index"] : null;
    const title = stringOrEmpty(item["name"]) || "Card";
    return [
      {
        key: stringOrEmpty(item["key"]) || `${deckIndex ?? index}-${title}`,
        title,
        effect: stringOrEmpty(item["description"]),
        serial: "",
        hidden: item["is_hidden"] === true,
        currentTarget: item["is_current_target"] === true,
      },
    ];
  });
}

export function selectCurrentHandTrayCards(
  messages: InboundMessage[],
  locale: string,
  preferredPlayerId: number | null
): HandTrayCardViewModel[] {
  const backendHandTray = selectBackendHandTrayCards(messages);
  if (backendHandTray) {
    return backendHandTray;
  }

  if (preferredPlayerId === null) {
    return [];
  }

  const activePrompt = selectActivePrompt(messages);
  if (activePrompt && activePrompt.playerId === preferredPlayerId) {
    const currentPromptCards = handTrayCardsFromPublicContext(activePrompt.publicContext, locale);
    if (currentPromptCards.length > 0) {
      return currentPromptCards;
    }
  }

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "prompt") {
      continue;
    }
    const messagePlayerId = typeof message.payload["player_id"] === "number" ? message.payload["player_id"] : null;
    if (messagePlayerId !== preferredPlayerId) {
      continue;
    }
    const publicContext = isRecord(message.payload["public_context"]) ? message.payload["public_context"] : null;
    if (!publicContext) {
      continue;
    }
    const persistedCards = handTrayCardsFromPublicContext(publicContext, locale);
    if (persistedCards.length > 0) {
      return persistedCards;
    }
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
