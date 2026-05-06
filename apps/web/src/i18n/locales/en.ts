export const enLocale = {
  app: {
    title: "MRN",
    subtitle: "Create a room with friends or jump straight into a match with 3 AI players.",
    routeLobby: "Lobby",
    routeMatch: "Match",
    connectionExpand: "Show connection status",
    connectionCollapse: "Hide connection status",
    densityStandard: "Standard density",
    densityCompact: "Compact density",
    rawShow: "Debug log",
    rawHide: "Close debug log",
    rawMessages: "Debug log",
    localeKo: "Korean",
    localeEn: "English",
    waitingTitle: (playerId: number) => `Waiting for player P${playerId} to choose.`,
    waitingDescription: "Even when it is not your turn, the board and theater keep showing public progress.",
    myTurnWaitingTitle: "Preparing your turn",
    myTurnWaitingDescription: (beatLabel: string, beatDetail: string) =>
      enLocale.app.inlineSummary(["Loading your next decision", beatLabel, beatDetail]),
    passivePromptTitle: "Another player is choosing",
    passivePromptSummary: (playerId: number, promptLabel: string, secondsLeft: number | null) =>
      `P${playerId} / ${promptLabel} / ${secondsLeft ?? "-"}s left`,
    spectatorTitle: (playerId: number) => `P${playerId} in progress`,
    spectatorDescription: "Shows the public flow while another player is acting.",
    spectatorHeadline: "Spectator Panel",
    inlineSummary: (parts: string[]) => {
      const visible = parts.map((part) => part.trim()).filter((part) => part && part !== "-");
      return visible.length > 0 ? visible.join(" / ") : "-";
    },
    spectatorEconomySummary: (parts: string[]) => enLocale.app.inlineSummary(parts),
    spectatorEffectSummary: (parts: string[]) => enLocale.app.inlineSummary(parts),
    spectatorSpotlightSummary: (parts: string[]) => enLocale.app.inlineSummary(parts),
    spectatorNeutralSummary: (parts: string[]) => enLocale.app.inlineSummary(parts),
    spectatorHeadlineSummary: (headline: string, summary: string) => enLocale.app.inlineSummary([headline, summary]),
    spectatorFields: {
      weather: "Weather",
      character: "Current character",
      beat: "Beat",
      action: "Public action",
      prompt: "Current choice",
      worker: "Participant status",
      move: "Latest move",
      landing: "Landing",
      economy: "Economy",
      effect: "Effect",
      progress: "Turn flow",
      commonEffect: "Common effect",
    },
    topSummaryEmpty: "Select a session",
    topSummary: (sessionId: string, runtimeStatus: string) => `Session ${sessionId} / ${runtimeStatus}`,
    turnBanner: (actorText: string) => `${actorText}'s turn`,
    reopenPrompt: (promptLabel: string, secondsLeft: number | null) =>
      `Reopen choice: ${promptLabel} / ${secondsLeft ?? "-"}s left`,
    errors: {
      refreshSessions: "Failed to load the session list.",
      sendPrompt: "Failed to submit the choice. Please try again.",
      invalidPromptPlayer: "The prompt has no player_id.",
      promptRejected: (reason?: string) => (reason ? `Choice rejected. ${reason}` : "Choice rejected."),
      promptStale: (reason?: string) => (reason ? `Choice is stale or already handled. ${reason}` : "Choice is stale or already handled."),
      promptTimedOut: "Choice time expired. The engine will continue with the fallback.",
      promptConnectionLost: "Connection was interrupted. Please wait for reconnect.",
      createSession: "Failed to create a session.",
      startAiSession: "Failed to start the AI session.",
      quickStart: "Failed to quick start.",
      startByHostTokenMissing: "Enter both session ID and host token.",
      startSession: "Failed to start the session.",
      joinSeatMissing: "Enter session ID, seat, and join token.",
      joinSeatFailed: "Failed to join the seat.",
      joinSeatNotWaiting: "The session is not in waiting state.",
      joinSeatNotFound: (seat: number) => `Seat ${seat} was not found.`,
      joinSeatNotHuman: (seat: number) => `Seat ${seat} is not a human seat.`,
    },
    notices: {
      createSession: (sessionId: string, hostToken: string, joinTokens: Record<string, string>) =>
        `Session created: ${sessionId} / host_token=${hostToken} / join_tokens=${JSON.stringify(joinTokens)}`,
      startAiSession: (sessionId: string) => `AI session started: ${sessionId}`,
      quickStart: (sessionId: string, playerId: number) => `Quick start ready: ${sessionId} (P${playerId})`,
      startSession: (sessionId: string) => `Session started: ${sessionId}`,
      joinSeat: (playerId: number) => `Joined as P${playerId}`,
      useSession: (sessionId: string) => `Using session: ${sessionId}`,
    },
  },
  lobby: {
    controlsTitle: "Lobby Controls",
    createSessionTitle: "Create Session",
    createSessionDescription: "Create a new session and choose the human/AI seat setup.",
    hostJoinTitle: "Host / Join",
    hostJoinDescription: "Start an existing session or join a human seat.",
    streamTitle: "Stream Connection",
    sessionListTitle: (count: number) => `Session List (${count})`,
    expand: "Expand",
    collapse: "Collapse",
    fields: {
      seed: "Seed",
      seatCount: "Seat Count (1-4)",
      aiProfile: "AI Profile",
      sessionId: "Session ID",
      hostToken: "Host Token",
      joinSeat: "Join Seat",
      joinToken: "Join Token",
      displayName: "Display Name",
      sessionToken: "Session Token (optional)",
    },
    buttons: {
      quickStartHumanVsAi: "Quick start: 1 human + 3 AI",
      createCustomSession: "Create custom session",
      createAndStartAi: "Create + start AI session",
      startSession: "Start session",
      joinAndConnect: "Join and connect",
      connect: "Connect",
      refreshSessions: "Refresh sessions",
      useSession: "Use this session",
      useSeatToken: (seat: string) => `Use seat ${seat} token`,
    },
    placeholders: {
      sessionId: "sess_xxx",
      hostToken: "host_xxx",
      joinToken: "seat_join_token",
      sessionToken: "session_p1_xxx (leave blank for spectator)",
    },
    labels: {
      latestCreateTokens: "Latest created join tokens",
    },
    values: {
      human: "human",
      ai: "ai",
      seat: (seat: string) => `Seat ${seat}`,
    },
  },
  connection: {
    title: "Connection",
    fields: {
      connection: "Connection",
      lastSequence: "Last seq",
      runtime: "Runtime",
      watchdog: "Watchdog",
      lastActivityMs: "Last activity (ms)",
    },
    runtimeStatus: {
      running: "running",
      completed: "completed",
      failed: "failed",
      recovery_required: "recovery required",
    },
    watchdogStatus: {
      ok: "ok",
      stalled_warning: "warning",
    },
  },
  board: {
    title: "Board",
    loading: "Waiting for board data.",
    manifestBoard: "Board initialized from the parameter manifest.",
    roundTurnMarker: (round: number, turn: number, markerOwner: number | null, endTimeRemaining: number | null) =>
      `Round ${round} / Turn ${turn} / Marker P${markerOwner ?? "-"} / End time ${endTimeRemaining?.toFixed(2) ?? "-"}`,
    lastMove: (playerId: number | null, fromTileIndex: number | null, toTileIndex: number | null) =>
      `Latest move: P${playerId ?? "?"} ${fromTileIndex === null ? "?" : fromTileIndex + 1} -> ${toTileIndex === null ? "?" : toTileIndex + 1}`,
    zoneLabel: (zoneColor: string) => (zoneColor ? `Zone ${zoneColor}` : "Zone -"),
    costLabel: (cost: number | null, rent: number | null) => {
      const purchase = cost === null ? "-" : `${cost} nyang`;
      const rentText = rent === null ? "-" : `${rent} nyang`;
      return `Buy ${purchase} / Rent ${rentText}`;
    },
    tilePrice: {
      purchase: "Buy",
      rent: "Rent",
      unit: "N",
    },
    ownerNone: "Owner -",
    owner: (playerId: number) => `Owner P${playerId}`,
    scoreCoins: (value: number) => `Score ${value}`,
    moveStartTag: "Start",
    moveEndTag: "Arrive",
    activeTurnTag: (playerId: number) => `Active P${playerId}`,
    zoneColorCss: {
      "": "#475569",
      black: "#475569",
      red: "#ef4444",
      yellow: "#eab308",
      blue: "#3b82f6",
      green: "#22c55e",
      white: "#e2e8f0",
    },
    tileKind: {
      S: "Fortune",
      F1: "End - 1",
      F2: "End - 2",
      T2: "Land",
      T3: "Land",
    },
  },
  players: {
    title: "Players",
    waiting: "Waiting for player data.",
    stats: {
      position: (value: number) => `Pos ${value}`,
      cash: (value: number) => `Cash ${value}`,
      shards: (value: number) => `Shards ${value}`,
      tiles: (value: number) => `Tiles ${value}`,
      hidden: (value: number) => `Hidden ${value}`,
    },
  },
  timeline: {
    title: (count: number) => `Recent Events (${count})`,
  },
  situation: {
    title: "Situation",
    cards: {
      actor: "Actor",
      roundTurn: "Round / Turn",
      event: "Event",
      weather: "Weather",
      weatherEffect: "Weather effect",
    },
    roundTurn: (round: string, turn: string) => `Round ${round} / Turn ${turn}`,
    empty: "-",
    alertsTitle: "Critical Alerts",
  },
  promptType: {
    generic: "Decision Request",
    labels: {
      movement: "Movement",
      runaway_step_choice: "Runaway Movement Choice",
      lap_reward: "Lap Reward",
      draft_card: "Draft Character Pick",
      final_character: "Final Character",
      final_character_choice: "Final Character",
      trick_to_use: "Use Trick",
      purchase_tile: "Purchase Tile",
      hidden_trick_card: "Hidden Trick",
      mark_target: "Mark Target",
      coin_placement: "Coin Placement",
      geo_bonus: "Geo Bonus",
      doctrine_relief: "Doctrine Relief",
      active_flip: "Active Flip",
      specific_trick_reward: "Specific Trick Reward",
      burden_exchange: "Burden Exchange",
      trick_tile_target: "Trick Tile Target",
      pabal_dice_mode: "Pabal Dice Mode",
    },
  },
  promptHelper: {
    default: "Pick a choice to send it to the engine. If time runs out, the default response is used.",
    byType: {
      movement: "Roll dice or use dice cards to decide this turn's movement value.",
      runaway_step_choice: "Choose one of the available movement routes.",
      lap_reward: "Choose a cash/shard/point bundle within the 10-point lap reward budget.",
      draft_card: "Take one character candidate during the draft step.",
      final_character: "Choose the final character.",
      final_character_choice: "Choose the final character.",
      trick_to_use: "Choose a trick to use now, or skip it.",
      purchase_tile: "Decide whether to buy the tile you landed on.",
      hidden_trick_card: "Choose which trick becomes hidden this round.",
      mark_target: "Choose the target affected by the mark effect.",
      coin_placement: "Choose where to place the point token.",
      geo_bonus: "Choose the geo bonus effect.",
      doctrine_relief: "Choose the target of Doctrine Researcher relief.",
      active_flip: "Choose a card to flip, or finish flipping.",
      specific_trick_reward: "Choose the trick reward.",
      burden_exchange: "A supply step opened a burden cleanup window. Decide whether to pay now and remove the burden card.",
      trick_tile_target: "Choose the tile affected by this trick card.",
      pabal_dice_mode: "Choose whether to roll three dice or reduce the roll to one die this turn.",
    },
  },
  eventLabel: {
    events: {
      session_started: "Session started",
      parameter_manifest: "Manifest sync",
      round_start: "Round start",
      weather_reveal: "Weather reveal",
      draft_pick: "Draft pick",
      final_character_choice: "Final character",
      turn_start: "Turn start",
      dice_roll: "Movement value",
      player_move: "Player move",
      trick_used: "Trick used",
      fortune_drawn: "Fortune drawn",
      fortune_resolved: "Fortune resolved",
      tile_purchased: "Tile purchased",
      rent_paid: "Rent paid",
      landing_resolved: "Landing result",
      marker_transferred: "Marker transferred",
      marker_flip: "Card flip",
      lap_reward_chosen: "Lap reward",
      decision_requested: "Decision requested",
      decision_resolved: "Decision resolved",
      decision_timeout_fallback: "Decision timeout fallback",
      mark_queued: "Mark queued",
      mark_target_none: "No legal mark target",
      mark_target_missing: "Missing mark target",
      mark_blocked: "Mark blocked",
      ability_suppressed: "Character ability blocked",
      active_flip_resolved: "Active flip resolved",
      bankruptcy: "Bankruptcy",
      game_end: "Game end",
      game_completed: "Game completed",
    },
    nonEvents: {
      prompt: "Prompt",
      decision_ack: "Decision Ack",
      system: "System",
      notice: "Notice",
      error: "Error",
    },
    genericEvent: "Event",
    genericMessage: "Message",
  },
  stream: {
    genericEvent: "Event",
    weatherEffectFallback: {
      "사냥의 계절": "Rogue characters gain 4 extra nyang when a mark succeeds.",
      "풍년든 가을": "Gain 1 extra shard when passing Start.",
      "말이 살찌는 계절": "Roll one extra die this turn.",
      "외세의 침략": "Every participant pays 2 nyang to the bank.",
      "솔선 수범": "The marker owner pays 3 nyang to the bank.",
      "기우제": "The marker owner gains 1 shard and the end track moves 1 step earlier.",
      "구휼의 상징": "The marker owner receives 4 nyang from the bank.",
      "성물의 날": "Gain 1 extra shard whenever you gain shards.",
      "모든 것을 자원으로": "Remove all burden cards and gain double their cleanup cost from the bank.",
      "긴급 피난": "All burden cleanup costs are doubled.",
      "대규모 민란": "Unowned land is treated as a contested region this turn.",
      "운수 좋은 날": "Reveal two fortune cards when landing on a fortune tile.",
      "검은 달": "Black-zone land charges double rent.",
      "휴가철": "Red-zone land charges double rent.",
      "어린이 보호구역": "Yellow-zone land charges double rent.",
      "바다다!": "Blue-zone land charges double rent.",
      "멋진 설경": "White-zone land charges double rent.",
      "곡식가득한 평야": "Green-zone land charges double rent.",
      "밤인데 낮처럼 밝아요": "Move the end track 3 spaces earlier.",
      "길고 긴 겨울": "Move the end track 1 space earlier.",
      "추운 겨울날": "No pass-start reward, and pay 2 nyang to the bank.",
      "사랑과 우정": "Gain 4 nyang per participant when players meet on the same tile.",
      "잔꾀 부리기": "Draw 1 trick and optionally replace an old trick.",
      "아주 큰 화목 난로": "This round reduces burden damage.",
      "배신의 징표": "No additional effect right now.",
      "맑고 포근한 하루": "Choose and gain one dice card.",
    } as const,
    genericEffect: (name: string) => `${name} effect`,
    moveSummary: (fromDisplay: string, toDisplay: string, pathLength?: number) =>
      typeof pathLength === "number" && pathLength > 0 ? `${fromDisplay} -> ${toDisplay} (path ${pathLength})` : `${fromDisplay} -> ${toDisplay}`,
    landingResultAt: (summary: string, tileDisplay: string) => `${summary} / tile ${tileDisplay}`,
    diceCard: (cards: string) => `Dice card ${cards}`,
    diceRoll: (dice: string) => `Dice ${dice}`,
    diceTotalSummary: (cardText: string, diceText: string, total: string | number) => {
      if (cardText && diceText) {
        return `${cardText} + ${diceText} = ${total}`;
      }
      if (cardText) {
        return `${cardText} = ${total}`;
      }
      if (diceText) {
        return `${diceText} = ${total}`;
      }
      return String(total);
    },
    landing: {
      purchaseSkip: "Skip purchase",
      purchase: "Purchase tile",
      rent: "Pay rent",
      markResolved: "Mark resolved",
      default: "Landing result",
    },
    heartbeat: {
      detail: (interval: number, dropCount: number) => `interval ${interval}ms / drop ${dropCount}`,
      interval: (interval: string) => `interval ${interval}`,
    },
    playerLabel: (playerId: number | string) => `P${playerId}`,
    readyStateLabel: (readyState: string) => {
      if (readyState === "ready") {
        return "state ready";
      }
      if (readyState === "not_ready") {
        return "state not_ready";
      }
      return `state ${readyState}`;
    },
    workerModeSummary: (policyMode?: string, workerAdapter?: string, policyClass?: string, decisionStyle?: string) => {
      const parts: string[] = [];
      if (policyMode && policyMode !== "-") {
        parts.push(`mode ${policyMode}`);
      }
      if (workerAdapter && workerAdapter !== "-") {
        parts.push(`adapter ${workerAdapter}`);
      }
      if (policyClass && policyClass !== "-") {
        parts.push(`class ${policyClass}`);
      }
      if (decisionStyle && decisionStyle !== "-") {
        parts.push(`style ${decisionStyle}`);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    actorDetail: (actor: string, detail: string) => `${actor} / ${detail}`,
    effectsList: (parts: string[]) => {
      const visible = parts.filter((part) => part && part.trim() && part.trim() !== "-");
      return visible.length > 0 ? visible.join(", ") : "-";
    },
    promptDetail: (actor: string, promptLabel: string) => `${actor} / ${promptLabel}`,
    decisionRequestedDetail: (
      actor: string,
      promptLabel: string,
      tileDisplay?: string,
      choiceCount?: number | null,
      workerSummary?: string
    ) => {
      const parts = [actor, promptLabel];
      if (tileDisplay && tileDisplay !== "-") {
        parts.push(`tile ${tileDisplay}`);
      }
      if (typeof choiceCount === "number" && choiceCount > 0) {
        parts.push(`${choiceCount} choices`);
      }
      if (workerSummary && workerSummary !== "-") {
        parts.push(workerSummary);
      }
      return parts.join(" / ");
    },
    decisionAckDetail: (status: string, reason: string) => (reason && reason !== "-" ? `${status} (${reason})` : status),
    decisionResolvedDetail: (resolution: string, choice: string, workerSummary?: string) => {
      const head = choice && choice !== "-" ? `${resolution} (${choice})` : resolution;
      return workerSummary && workerSummary !== "-" ? `${head} / ${workerSummary}` : head;
    },
    decisionTimeoutFallbackDetail: (
      summary: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts = ["Timeout fallback"];
      if (summary && summary !== "-") {
        parts.push(summary);
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`failure ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`fallback ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `attempt ${attemptCount}/${attemptLimit}` : `attempt ${attemptCount}`);
      }
      const modeSummary = enLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.join(" / ");
    },
    workerStatusDetail: (
      workerLabel: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      readyState?: string,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts: string[] = [];
      if (workerLabel && workerLabel !== "-") {
        parts.push(workerLabel);
      }
      if (readyState && readyState !== "-") {
        parts.push(enLocale.stream.readyStateLabel(readyState));
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`failure ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`fallback ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `attempt ${attemptCount}/${attemptLimit}` : `attempt ${attemptCount}`);
      }
      const modeSummary = enLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    weatherDetail: (weather: string, effect: string) => (effect && effect !== "-" ? `${weather} / ${effect}` : weather),
    errorDetail: (code: string, message: string) => (code && code !== "-" ? `${code}: ${message}` : message),
    stalledWarning: (text: string) => `Runtime warning: ${text}`,
    tilePurchased: (tileDisplay: string, cost: unknown) => `Bought tile ${tileDisplay} for ${cost}`,
    markerTransferred: (from: unknown, to: unknown, flipped?: unknown) =>
      typeof flipped === "number" ? `[Marker] P${from} -> P${to} (flip P${flipped})` : `[Marker] P${from} -> P${to}`,
    markQueued: (source: unknown, target: unknown, targetCharacter: string, effectType: string) => {
      const effect =
        effectType === "bandit_tax"
          ? "Bandit"
          : effectType === "hunter_pull"
            ? "Hunter"
            : effectType === "baksu_transfer"
              ? "Baksu"
              : effectType === "manshin_remove_burdens"
                ? "Manshin"
                : "Mark";
      return `[${effect}] P${source} -> P${target} / ${targetCharacter} / queued first at target turn start`;
    },
    markTargetNone: (source: unknown, actorName: string) => `${actorName || `P${source}`} / no legal mark target, fallback applied`,
    markTargetMissing: (source: unknown, targetCharacter: string) =>
      `P${source} / could not find ${targetCharacter || "-"} in the remaining turn order`,
    markBlocked: (source: unknown, target: unknown, targetCharacter: string) =>
      `P${source} / mark on P${target}${targetCharacter ? ` (${targetCharacter})` : ""} was blocked because the target was already revealed`,
    abilitySuppressed: (source: unknown, actorName: string, reason: string) =>
      `${actorName || `P${source}`} ability blocked / ${
        reason === "muroe_blocked_by_eosa" ? "Eosa blocks Muroe character abilities" : reason || "effect was not applied"
      }`,
    markerFlipDetail: (from: string, to: string) => `${from} -> ${to}`,
    rentPaid: (payer: unknown, owner: unknown, amount: unknown, tileDisplay: string) =>
      `P${payer} paid P${owner} ${amount} on tile ${tileDisplay}`,
    fortuneDrawn: (cardName: string) => `Fortune card: ${cardName}`,
    fortuneResolved: (summary: string) => `Fortune effect: ${summary}`,
    lapRewardChosen: (actor: string, reward: string) => `${actor} / ${reward}`,
    lapRewardBundle: (parts: string[]) => enLocale.app.inlineSummary(parts),
    bankruptcy: (pid: unknown) => `P${pid} bankrupt`,
    winner: (winner: number) => `Winner P${winner}`,
    gameEndDefault: "Game end",
    lapReward: {
      cash: (cash: number) => `Cash +${cash}`,
      shards: (shards: number) => `Shards +${shards}`,
      coins: (coins: number) => `Points +${coins}`,
    },
    manifestSync: "Manifest sync",
    manifestSyncHash: (hash: string) => `Manifest sync ${hash}`,
    markResolved: (source: number, target: number) => `[Mark] P${source} -> P${target}`,
    markerFlip: "Card flip",
    fValueChange: {
      detail: (before: number, delta: number, after: number) => `End time ${before} + (${delta}) = ${after}`,
      label: "End time changed",
    },
    runtimeError: "Runtime error",
    promptWaiting: (promptLabel: string) => `${promptLabel} pending`,
  },
  theater: {
    coreActionTitle: "Recent Public Actions",
    coreActionDescription: "Shows movement, purchase, rent, fortune, weather, and other public action flow.",
    payoffSceneTitle: "Same-Turn Payoff Beats",
    turnFlowTitle: "Same Turn Flow",
    turnFlowEmpty: "No connected public actions in this turn yet.",
    roundTurnBadge: (round: number | null, turn: number | null) =>
      round !== null && turn !== null ? `Round ${round} / Turn ${turn}` : "Round / Turn unavailable",
    latestPublicAction: "Latest public action",
    noDetail: "No extra detail",
    actionKind: {
      move: "Move",
      economy: "Economy",
      effect: "Effect",
      decision: "Decision",
      system: "System",
    },
    actionKeywords: {
      move: ["move", "dice"],
      economy: ["purchase", "rent", "cash", "shard", "coin"],
      effect: ["fortune", "weather", "trick", "flip", "mark"],
      decision: ["decision", "prompt", "target"],
    } as const,
    toneBadge: {
      move: "Move",
      economy: "Economy",
      critical: "Critical",
      system: "System",
    },
    panelLead: {
      move: "Shows movement and destination first.",
      economy: "Summarizes purchase, rent, reward, and cost changes.",
      effect: "Shows weather, fortune, trick, and card effects.",
      decision: "Shows prompt and response flow.",
      system: "Shows connection, recovery, warnings, and errors.",
    },
    detailHeading: {
      move: "Move detail",
      economy: "Economy detail",
      effect: "Effect detail",
      decision: "Decision detail",
      system: "System detail",
    },
    payoffBeat: {
      tile_purchased: "Purchase resolved",
      rent_paid: "Rent paid",
      fortune_drawn: "Fortune revealed",
      fortune_resolved: "Fortune effect",
      lap_reward_chosen: "Reward resolved",
    },
    payoffBeatIndex: (index: number, total: number, label: string) => `${index}/${total} ${label}`,
    incidentTitle: "Turn Theater",
    incidentDescription: "Separates turn progress, decision prompts, and system records.",
    laneBadge: {
      core: "Core",
      prompt: "Prompt",
      system: "System",
    },
    laneTitle: {
      core: "Turn Progress",
      prompt: "Decision Requests",
      system: "System Records",
    },
    laneDescription: {
      core: "Shows public movement, purchase, rent, fortune, and effects.",
      prompt: "Shows decision requests, responses, and fallback handling.",
      system: "Shows connection status, recovery, warnings, and errors.",
    },
    laneEmpty: {
      core: "No public actions yet.",
      prompt: "No prompt records yet.",
      system: "No system records yet.",
    },
    expand: "Expand",
    collapse: "Collapse",
  },
  turnStage: {
    title: "Turn Stage",
    description: "Groups weather, character, movement, landing, and card effects around the current turn.",
    myTurn: "My turn",
    observing: "Observing",
    actorHeadline: (actor: string) => `${actor} in progress`,
    actorWaiting: "Waiting for actor info",
    weatherTitle: "Round Weather",
    weatherBadge: "Weather",
    characterTitle: "Chosen Character",
    characterBadge: "Character",
    movementTitle: "Movement",
    movementBadge: "Dice / Move",
    landingTitle: "Landing",
    landingBadge: "Purchase / Rent",
    cardEffectTitle: "Card Effect",
    cardEffectBadge: "Trick / Fortune",
    currentBeatTitle: "Current Beat",
    currentBeatBadge: "Beat",
    sceneSequenceTitle: "Turn Scene",
    sceneSequenceBadge: "Scene",
    resultSequenceTitle: "Turn Results",
    resultSequenceBadge: "Results",
    progressTitle: "Turn Flow",
    progressBadge: "Flow",
    workerTitle: "Participant Status",
    workerBadge: "worker",
    actorStatusTitle: "Current Actor Status",
    actorStatusBadge: "Resources",
    fields: {
      dice: "Dice",
      move: "Move",
      landing: "Landing",
      purchase: "Purchase",
      rent: "Rent",
      trick: "Trick",
      fortune: "Fortune",
      decision: "Decision",
      beat: "Current action",
      cash: "Cash",
      shards: "Shards",
      handCoins: "Hand points",
      placedCoins: "Placed points",
      totalScore: "Total score",
      ownedTiles: "Owned tiles",
    },
    promptIdle: "No active prompt",
    progressEmpty: "No turn progress yet.",
    workerStatusLabel: (status: string) => {
      if (status === "pending") {
        return "External worker pending";
      }
      if (status === "resolved_by_worker") {
        return "Resolved by external worker";
      }
      if (status === "worker_failed") {
        return "External worker failed";
      }
      if (status === "resolved_by_local_fallback") {
        return "Resolved by local fallback";
      }
      return status || "-";
    },
    workerStatusSummary: (
      status: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      readyState?: string,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts: string[] = [];
      const label = status && status !== "-" ? enLocale.turnStage.workerStatusLabel(status) : "";
      if (label) {
        parts.push(label);
      }
      if (readyState && readyState !== "-") {
        parts.push(enLocale.stream.readyStateLabel(readyState));
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`failure ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`fallback ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `attempt ${attemptCount}/${attemptLimit}` : `attempt ${attemptCount}`);
      }
      const modeSummary = enLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    weatherSummaryLine: (weatherName: string, weatherEffect: string) =>
      weatherEffect && weatherEffect !== "-" ? `${weatherName} / ${weatherEffect}` : weatherName,
    roundTurnLabel: (round: number | null, turn: number | null) => `R${round ?? "-"} / T${turn ?? "-"}`,
    turnStartDetail: (actor: string) => `${actor} / turn start`,
    sequenceIndex: (index: number, total: number) => `${index}/${total}`,
    sequenceBeat: {
      weather: "Apply the weather for this turn",
      purchase: "Purchase check after landing",
      rent: "Rent settlement on an owned tile",
      fortuneDraw: "Reveal the fortune card",
      fortuneResolved: "Apply the fortune effect",
      lapReward: "Resolve the completed-lap reward",
      mark: "Resolve the mark target effect",
      flip: "Flip the current active card",
    },
  },
  prompt: {
    noChoiceDescription: "No choices available yet.",
    effectContextLabel: "Previous result",
    effectAttribution: {
      characterMark: "Character mark",
      trickEffect: "Trick effect",
      movementResult: "Movement result",
      characterEffect: "Character effect",
      supplyThreshold: "Supply threshold",
      roundEnd: "Round end",
      scorePlacement: "Score placement",
    },
    hiddenCardName: "Hidden Card",
    hiddenCardDescription: (name: string) => `${name} effect`,
    hiddenState: {
      hidden: "Hidden trick",
      public: "Public trick",
      usable: "Usable",
      unavailable: "Unavailable now",
    },
    collapsedChip: (label: string, secondsLeft: number | null) => `Decision: ${label} / ${secondsLeft ?? "-"}s left`,
    headTitle: (label: string) => `Decision: ${label}`,
    collapse: "Collapse",
    expand: "Expand",
    secondaryChoiceBadge: "Secondary",
    requestMetaPills: (playerId: number, timeoutMs: number, secondsLeft: number | null) => [
      `Actor P${playerId}`,
      `Limit ${Math.ceil(timeoutMs / 1000)}s`,
      `${secondsLeft ?? "-"}s left`,
    ],
    requestCompactMetaPills: (playerId: number, secondsLeft: number | null) => [`P${playerId}`, `${secondsLeft ?? "-"}s left`],
    requestMeta: (_requestId: string, playerId: number, timeoutMs: number, secondsLeft: number | null) =>
      `Actor P${playerId} / limit ${Math.ceil(timeoutMs / 1000)}s / ${secondsLeft ?? "-"}s left`,
    context: {
      currentPosition: "Current position",
      usableCards: "Usable cards",
      selectedCards: "Selected cards",
      currentWeather: "Current weather",
      actorCharacter: "Acting character",
      selectableTargets: "Selectable targets",
      targetRule: "Mark rule",
      trigger: "Trigger",
      burdenCard: "Burden card",
      burdenCost: "Removal cost",
      currentF: "Current F",
      supplyThreshold: "Supply threshold",
      purchaseCost: "Purchase cost",
      currentCash: "Current cash",
      zone: "Zone",
      currentShards: "Current shards",
      currentCoins: "Current points",
      currentPlacedCoins: "Placed points",
      currentTotalScore: "Total score",
      ownedTiles: "Owned tiles",
      rewardBudget: "Required reward budget",
      rewardPools: "Reward pool",
      draftPhase: "Draft phase",
      targetTiles: "Target tiles",
      noneSelected: "None",
      burdenExchangeTrigger: (threshold: number | null, currentF: number | null) => {
        if (threshold !== null && currentF !== null) {
          return `Supply step (F ${currentF} / threshold ${threshold})`;
        }
        if (threshold !== null) {
          return `Supply step (threshold F ${threshold})`;
        }
        return "Supply step";
      },
      markTargetRule: (targetCount: number | null) =>
        targetCount === 0
          ? "No unrevealed later-turn character is available to mark in this round."
          : "You may only mark unrevealed characters that act later in this round.",
    },
    movement: {
      rollMode: "Roll dice",
      cardMode: "Use dice cards",
      cardGuide: (limit: number) => `Choose up to ${limit} dice card${limit > 1 ? "s" : ""}, then roll.`,
      rollButton: "Roll dice now",
      rollWithCardsButton: (cards: number[]) => `Roll with cards ${cards.join(", ")}`,
      selectCardsFirst: "Select dice cards first",
    },
    trick: {
      usePrompt: "Choose a trick for this turn.",
      hiddenPrompt: "Choose which trick will stay hidden this round.",
      handSummary: (count: number, hiddenCount?: number) =>
        `Hand ${count}${typeof hiddenCount === "number" ? ` / hidden ${hiddenCount}` : ""}`,
      skipTitle: "Do not use a trick",
      skipDescription: "Proceed without using a trick.",
    },
    character: {
      draftPrompt: "Take one candidate from the draft.",
      finalPrompt: "Choose the final character.",
      ability: (name: string) => `${name} ability`,
      draftPhaseLabel: (phase: number | null) => (phase !== null ? `Draft phase ${phase}` : "Draft"),
      draftForwardPrompt: (count: number | null) =>
        `Draft phase 1: choose one card starting from the marker owner in marker direction.${count !== null ? ` ${count} option${count === 1 ? "" : "s"} now.` : ""}`,
      draftReversePrompt: (count: number | null) =>
        `Draft phase 2: choose one card in reverse order from phase 1.${count !== null ? ` ${count} option${count === 1 ? "" : "s"} now.` : ""}`,
      finalPhaseLabel: "Final confirmation",
    },
    pabal: {
      plusOneTitle: "Roll three dice",
      plusOneDescription: "Use the front-side courier effect and add one die this turn.",
      minusOneTitle: "Roll one die",
      minusOneDescription: "Use the back-side courier effect and reduce the roll to one die this turn.",
    },
    mark: {
      noneTitle: "No mark",
      noneDescription: "Proceed without using the mark effect.",
      title: (target: string) => target,
      description: (targetCharacter: string, targetPlayerId: number) => `Target character ${targetCharacter} / player P${targetPlayerId}`,
      fallbackDescription: "Choose a mark target.",
    },
    choice: {
      noChoices: "No selectable items.",
      cashTitle: "Choose cash",
      shardTitle: "Choose shards",
      coinTitle: "Choose points",
      cashReward: (amount: number) => `Cash +${amount}`,
      shardReward: (amount: number) => `Shards +${amount}`,
      coinReward: (amount: number) => `Points +${amount}`,
      mixedReward: (cash: number, shards: number, coins: number, spent: number | null, budget: number | null) => {
        const parts = [];
        if (cash > 0) parts.push(`Cash +${cash}`);
        if (shards > 0) parts.push(`Shards +${shards}`);
        if (coins > 0) parts.push(`Points +${coins}`);
        if (spent !== null && budget !== null) parts.push(`Required ${spent}/${budget}`);
        return parts.join(" / ");
      },
      buyTileTitle: "Buy tile",
      buyTile: (pos: number | null, cost: number | null) =>
        pos !== null && cost !== null ? `Tile ${pos + 1} / cost ${cost}` : "Buy the tile you landed on.",
      skipPurchaseTitle: "Skip purchase",
      skipPurchase: "End the current turn without buying.",
      endFlip: "Finish flipping",
      endFlipDescription: "Finish without flipping more cards.",
      flipChange: (current: string, next: string) => `${current} -> ${next}`,
      flipDescription: "Flip the chosen card to its opposite side.",
      exchangeBurden: "Exchange burden card",
      exchangeBurdenDescription: (cardName: string | null, cost: number | null, trigger: string) =>
        `${trigger}${cardName ? ` / ${cardName}` : ""}${cost !== null ? ` / cost ${cost}` : ""}`,
      keepBurdenTitle: "Keep it this time",
      keepBurdenDescription: (cardName: string | null, trigger: string) =>
        `${trigger}: keep${cardName ? ` ${cardName}` : " this burden card"} for now.`,
      skip: "Skip",
    },
    busy: "Submitting choice...",
  },
} as const;
