export type E2EManifestRecord = {
  manifest_version: number;
  manifest_hash: string;
  source_fingerprints: Record<string, string>;
  version: string;
  board?: {
    topology?: string;
    tile_count?: number;
    tiles?: Array<Record<string, unknown>>;
  };
  seats?: {
    min?: number;
    max?: number;
    allowed?: number[];
    default_profile_max?: number;
  };
  dice?: Record<string, unknown>;
  economy?: Record<string, unknown>;
  resources?: Record<string, unknown>;
};

export type E2EStreamMessage = {
  type: string;
  seq: number;
  session_id: string;
  server_time_ms: number;
  payload: Record<string, unknown>;
  delay_ms?: number;
};

export type E2ESessionSnapshot = {
  session_id?: string;
  status?: string;
  round_index?: number;
  turn_index?: number;
  initial_active_by_card?: Record<string, string> | null;
  seats?: Array<Record<string, unknown>>;
  parameter_manifest?: E2EManifestRecord | null;
};

const DEFAULT_CHARACTERS = [
  "산적",
  "객주",
  "파발꾼",
  "교리 감독관",
  "연구관",
  "어사",
  "박수",
  "만신",
  "중매꾼",
  "자객",
  "추노꾼",
  "아전",
  "Archivist",
  "Hidden",
  "Bandit",
  "Courier",
  "Surveyor",
  "Scholar",
  "Oracle",
  "Broker",
];

const WEATHER_EFFECT_BY_NAME: Record<string, string> = {
  "긴급 피난": "모든 짐 제거 비용이 2배가 됩니다.",
};

const CORE_EVENT_CODES = new Set([
  "round_start",
  "weather_reveal",
  "draft_pick",
  "final_character_choice",
  "turn_start",
  "dice_roll",
  "trick_used",
  "player_move",
  "landing_resolved",
  "rent_paid",
  "tile_purchased",
  "marker_transferred",
  "marker_flip",
  "lap_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "mark_resolved",
  "mark_queued",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "ability_suppressed",
  "bankruptcy",
  "game_end",
  "turn_end_snapshot",
  "decision_timeout_fallback",
]);

const REVEAL_EVENT_CODES = new Set([
  "weather_reveal",
  "dice_roll",
  "trick_used",
  "player_move",
  "landing_resolved",
  "tile_purchased",
  "rent_paid",
  "lap_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "mark_queued",
  "mark_resolved",
  "ability_suppressed",
  "marker_flip",
  "marker_transferred",
  "bankruptcy",
  "game_end",
]);

type RevealTone = "move" | "effect" | "economy";
type TheaterTone = "move" | "economy" | "system" | "critical";

type RevealItem = {
  seq: number;
  event_code: string;
  label: string;
  detail: string;
  tone: RevealTone;
  focus_tile_index: number | null;
  is_interrupt: boolean;
  effect_character?: string;
};

type CoreActionItem = {
  seq: number;
  event_code: string;
  actor_player_id: number | null;
  round_index: number | null;
  turn_index: number | null;
  detail: string;
};

type TheaterItem = CoreActionItem & {
  message_type: string;
  tone: TheaterTone;
  lane: "core" | "prompt" | "system";
};

type LastMove = {
  player_id: number | null;
  from_tile_index: number | null;
  to_tile_index: number | null;
  path_tile_indices: number[];
};

type TurnSummaries = {
  dice_summary: string;
  move_summary: string;
  trick_summary: string;
  landing_summary: string;
  purchase_summary: string;
  rent_summary: string;
  turn_end_summary: string;
  fortune_draw_summary: string;
  fortune_resolved_summary: string;
  fortune_summary: string;
  lap_reward_summary: string;
  mark_summary: string;
  flip_summary: string;
  weather_summary: string;
  effect_summary: string;
  prompt_summary: string;
};

type WorkerStatus = {
  external_ai_worker_id: string;
  external_ai_failure_code: string;
  external_ai_fallback_mode: string;
  external_ai_resolution_status: string;
  external_ai_attempt_count: number | null;
  external_ai_attempt_limit: number | null;
  external_ai_ready_state: string;
  external_ai_policy_mode: string;
  external_ai_worker_adapter: string;
  external_ai_policy_class: string;
  external_ai_decision_style: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function optionalString(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function eventLabel(eventCode: string): string {
  const labels: Record<string, string> = {
    weather_reveal: "Weather",
    dice_roll: "Dice roll",
    player_move: "Move",
    landing_resolved: "Landing",
    tile_purchased: "Purchase",
    rent_paid: "Rent paid",
    lap_reward_chosen: "Lap reward",
    fortune_drawn: "Fortune drawn",
    fortune_resolved: "Fortune effect",
    trick_used: "Trick",
    mark_queued: "Mark queued",
    mark_resolved: "Mark resolved",
    marker_flip: "Marker flip",
    marker_transferred: "Marker transferred",
    decision_timeout_fallback: "Decision timeout fallback",
    turn_end_snapshot: "Turn end",
    game_end: "게임 종료",
  };
  return labels[eventCode] ?? eventCode;
}

function revealTone(eventCode: string): RevealTone {
  if (eventCode === "dice_roll" || eventCode === "player_move") {
    return "move";
  }
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen") {
    return "economy";
  }
  return "effect";
}

function theaterTone(eventCode: string): TheaterTone {
  if (eventCode === "game_end" || eventCode === "bankruptcy" || eventCode === "trick_used") {
    return "critical";
  }
  if (revealTone(eventCode) === "move") {
    return "move";
  }
  if (revealTone(eventCode) === "economy") {
    return "economy";
  }
  return "system";
}

function turnBeatKind(eventCode: string): "move" | "economy" | "effect" | "decision" | "system" {
  if (eventCode === "dice_roll" || eventCode === "player_move") {
    return "move";
  }
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen") {
    return "economy";
  }
  if (
    eventCode === "decision_requested" ||
    eventCode === "decision_resolved" ||
    eventCode === "decision_timeout_fallback" ||
    eventCode === "draft_pick" ||
    eventCode === "final_character_choice"
  ) {
    return "decision";
  }
  if (REVEAL_EVENT_CODES.has(eventCode)) {
    return "effect";
  }
  return "system";
}

function focusTileIndex(payload: Record<string, unknown>, eventCode: string): number | null {
  const publicContext = isRecord(payload.public_context) ? payload.public_context : null;
  if (eventCode === "player_move") {
    return numberOrNull(payload.to_tile_index ?? payload.to_tile ?? payload.to_pos);
  }
  if (eventCode === "landing_resolved") {
    return numberOrNull(payload.position ?? payload.tile_index ?? payload.tile);
  }
  if (
    eventCode === "tile_purchased" ||
    eventCode === "rent_paid" ||
    eventCode === "fortune_drawn" ||
    eventCode === "fortune_resolved" ||
    eventCode === "trick_used"
  ) {
    return numberOrNull(
      payload.tile_index ??
        payload.position ??
        payload.end_pos ??
        payload.target_pos ??
        payload.tile ??
        publicContext?.tile_index ??
        publicContext?.position ??
        publicContext?.tile
    );
  }
  if (eventCode === "decision_requested" || eventCode === "decision_timeout_fallback" || eventCode === "decision_resolved") {
    return numberOrNull(publicContext?.tile_index ?? publicContext?.position ?? publicContext?.tile);
  }
  return null;
}

function payloadActor(payload: Record<string, unknown>, fallback: number): number {
  return numberValue(payload.acting_player_id, numberValue(payload.player_id, fallback));
}

function isInterruptEvent(eventCode: string): boolean {
  return (
    eventCode === "rent_paid" ||
    eventCode === "lap_reward_chosen" ||
    eventCode === "fortune_drawn" ||
    eventCode === "fortune_resolved" ||
    eventCode === "mark_queued" ||
    eventCode === "mark_resolved" ||
    eventCode === "marker_flip" ||
    eventCode === "marker_transferred" ||
    eventCode === "ability_suppressed" ||
    eventCode === "decision_timeout_fallback" ||
    eventCode === "bankruptcy" ||
    eventCode === "game_end"
  );
}

function sourcePath(payload: Record<string, unknown>): number[] {
  const path = Array.isArray(payload.path) ? payload.path : Array.isArray(payload.path_tile_indices) ? payload.path_tile_indices : [];
  return path.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
}

function effectCharacterName(payload: Record<string, unknown>): string {
  const resolution = isRecord(payload.resolution) ? payload.resolution : null;
  return (
    optionalString(payload.effect_character_name) ||
    optionalString(resolution?.effect_character_name) ||
    optionalString(payload.actor_name) ||
    optionalString(resolution?.actor_name)
  );
}

function stringifyAmount(amount: unknown): string {
  if (isRecord(amount)) {
    return Object.entries(amount)
      .map(([key, value]) => `${key} ${String(value)}`)
      .join(", ");
  }
  if (typeof amount === "number" || typeof amount === "string") {
    return String(amount);
  }
  return "";
}

function eventDetail(eventCode: string, payload: Record<string, unknown>): string {
  const summary = optionalString(payload.summary);
  if (summary) {
    return summary;
  }
  if (eventCode === "dice_roll") {
    const dice = Array.isArray(payload.dice_values) ? payload.dice_values : Array.isArray(payload.dice) ? payload.dice : [];
    const total = payload.total_move ?? payload.total ?? payload.move ?? "?";
    return `Dice ${dice.length > 0 ? dice.join("+") : "?"} / total ${String(total)}`;
  }
  if (eventCode === "player_move") {
    const actor = numberOrNull(payload.acting_player_id ?? payload.player_id);
    const from = numberOrNull(payload.from_tile_index ?? payload.from_tile ?? payload.from_pos);
    const to = numberOrNull(payload.to_tile_index ?? payload.to_tile ?? payload.to_pos);
    return `P${actor ?? "?"} ${from ?? "?"}->${to ?? "?"}`;
  }
  if (eventCode === "landing_resolved") {
    return optionalString(payload.result_type ?? payload.result_code ?? payload.result) || `Tile ${String(payload.tile_index ?? payload.position ?? "?")}`;
  }
  if (eventCode === "tile_purchased") {
    return `P${String(payload.player_id ?? payload.acting_player_id ?? "?")} bought tile ${String(payload.tile_index ?? "?")} for ${String(payload.cost ?? "?")}`;
  }
  if (eventCode === "rent_paid") {
    const payer = payload.payer_player_id ?? payload.player_id ?? "?";
    const owner = payload.owner_player_id ?? "?";
    const amount = payload.final_amount ?? payload.amount ?? payload.rent ?? "?";
    return `P${String(payer)} -> P${String(owner)} paid ${String(amount)}`;
  }
  if (eventCode === "lap_reward_chosen") {
    return `Lap reward ${stringifyAmount(payload.amount) || String(payload.choice ?? payload.reward ?? "")}`.trim();
  }
  if (eventCode === "mark_resolved" || eventCode === "mark_queued") {
    const resolution = isRecord(payload.resolution) ? payload.resolution : null;
    return optionalString(resolution?.summary) || `${optionalString(payload.actor_name) || "Mark"} / P${String(payload.source_player_id ?? payload.player_id ?? "?")} -> P${String(payload.target_player_id ?? "?")}`;
  }
  if (eventCode === "marker_flip") {
    return `${String(payload.from_character ?? "?")} -> ${String(payload.to_character ?? "?")}`;
  }
  if (eventCode === "weather_reveal") {
    return optionalString(payload.weather_effect ?? payload.effect_text ?? payload.effect) || WEATHER_EFFECT_BY_NAME[optionalString(payload.weather_name)] || "-";
  }
  if (eventCode === "turn_end_snapshot") {
    return optionalString(payload.reason) || "Turn closed";
  }
  return optionalString(payload.description ?? payload.effect_text ?? payload.reason) || eventCode;
}

function emptyTurnSummaries(): TurnSummaries {
  return {
    dice_summary: "-",
    move_summary: "-",
    trick_summary: "-",
    landing_summary: "-",
    purchase_summary: "-",
    rent_summary: "-",
    turn_end_summary: "-",
    fortune_draw_summary: "-",
    fortune_resolved_summary: "-",
    fortune_summary: "-",
    lap_reward_summary: "-",
    mark_summary: "-",
    flip_summary: "-",
    weather_summary: "-",
    effect_summary: "-",
    prompt_summary: "-",
  };
}

function emptyWorkerStatus(): WorkerStatus {
  return {
    external_ai_worker_id: "-",
    external_ai_failure_code: "-",
    external_ai_fallback_mode: "-",
    external_ai_resolution_status: "-",
    external_ai_attempt_count: null,
    external_ai_attempt_limit: null,
    external_ai_ready_state: "-",
    external_ai_policy_mode: "-",
    external_ai_worker_adapter: "-",
    external_ai_policy_class: "-",
    external_ai_decision_style: "-",
  };
}

function mergeWorkerStatus(status: WorkerStatus, publicContext: unknown): WorkerStatus {
  if (!isRecord(publicContext)) {
    return status;
  }
  return {
    ...status,
    external_ai_worker_id: optionalString(publicContext.external_ai_worker_id) || status.external_ai_worker_id,
    external_ai_failure_code: optionalString(publicContext.external_ai_failure_code) || status.external_ai_failure_code,
    external_ai_fallback_mode: optionalString(publicContext.external_ai_fallback_mode) || status.external_ai_fallback_mode,
    external_ai_resolution_status: optionalString(publicContext.external_ai_resolution_status) || status.external_ai_resolution_status,
    external_ai_attempt_count: numberOrNull(publicContext.external_ai_attempt_count) ?? status.external_ai_attempt_count,
    external_ai_attempt_limit: numberOrNull(publicContext.external_ai_attempt_limit) ?? status.external_ai_attempt_limit,
    external_ai_ready_state: optionalString(publicContext.external_ai_ready_state) || status.external_ai_ready_state,
    external_ai_policy_mode: optionalString(publicContext.external_ai_policy_mode) || status.external_ai_policy_mode,
    external_ai_worker_adapter: optionalString(publicContext.external_ai_worker_adapter) || status.external_ai_worker_adapter,
    external_ai_policy_class: optionalString(publicContext.external_ai_policy_class) || status.external_ai_policy_class,
    external_ai_decision_style: optionalString(publicContext.external_ai_decision_style) || status.external_ai_decision_style,
  };
}

function updateTurnSummaries(summaries: TurnSummaries, eventCode: string, detail: string): void {
  if (eventCode === "dice_roll") summaries.dice_summary = detail;
  if (eventCode === "player_move") summaries.move_summary = detail;
  if (eventCode === "trick_used") summaries.trick_summary = detail;
  if (eventCode === "landing_resolved") summaries.landing_summary = detail;
  if (eventCode === "tile_purchased") summaries.purchase_summary = detail;
  if (eventCode === "rent_paid") summaries.rent_summary = detail;
  if (eventCode === "turn_end_snapshot") summaries.turn_end_summary = detail;
  if (eventCode === "fortune_drawn") summaries.fortune_draw_summary = detail;
  if (eventCode === "fortune_resolved") {
    summaries.fortune_resolved_summary = detail;
    summaries.fortune_summary = detail;
  }
  if (eventCode === "lap_reward_chosen") summaries.lap_reward_summary = detail;
  if (eventCode === "mark_resolved" || eventCode === "mark_queued") summaries.mark_summary = detail;
  if (eventCode === "marker_flip") summaries.flip_summary = detail;
  if (eventCode === "weather_reveal") summaries.weather_summary = detail;
  if (eventCode === "decision_requested" || eventCode === "decision_resolved" || eventCode === "decision_timeout_fallback") {
    summaries.prompt_summary = detail;
  }
  if (eventCode === "ability_suppressed" || eventCode === "bankruptcy" || eventCode === "decision_timeout_fallback") {
    summaries.effect_summary = detail;
  }
}

function maxCommitSeq(messages: E2EStreamMessage[]): number {
  return messages.reduce((max, message) => {
    if (message.type !== "view_commit") {
      return max;
    }
    return Math.max(max, numberValue(message.payload.commit_seq, max));
  }, 0);
}

function playerIds(manifest: E2EManifestRecord | undefined, snapshot: E2ESessionSnapshot | undefined): number[] {
  const fromSeats = (snapshot?.seats ?? [])
    .map((seat) => numberValue(seat.player_id, numberValue(seat.seat, 0)))
    .filter((value) => value > 0);
  if (fromSeats.length > 0) {
    return Array.from(new Set(fromSeats));
  }
  const allowed = manifest?.seats?.allowed ?? [1, 2];
  return allowed.length > 0 ? allowed : [1, 2];
}

function activeCharacterSlots(activeByCard: Record<string, string>, character: string): Array<Record<string, unknown>> {
  const slotEntries = Object.entries(activeByCard)
    .map(([slot, name]) => ({ slot: Number(slot), name }))
    .filter((entry) => Number.isFinite(entry.slot) && entry.slot > 0 && entry.name)
    .sort((left, right) => left.slot - right.slot);
  if (slotEntries.length > 0) {
    return slotEntries.map((entry) => ({
      slot: entry.slot,
      character: entry.name,
      player_id: null,
      label: null,
      inactive_character: null,
      is_current_actor: entry.name === character,
    }));
  }
  const names = Array.from(new Set([...Object.keys(activeByCard), ...DEFAULT_CHARACTERS, character].filter(Boolean)));
  return names.map((name, index) => ({
    slot: index + 1,
    character: name,
    player_id: activeByCard[name] ? Number(activeByCard[name]) || null : null,
    label: activeByCard[name] ?? null,
    inactive_character: null,
    is_current_actor: name === character,
  }));
}

function playerCards(
  players: number[],
  activeByCard: Record<string, string>,
  actorPlayerId: number,
  character: string,
): Array<Record<string, unknown>> {
  const byPlayer = new Map<number, string>();
  for (const [card, owner] of Object.entries(activeByCard)) {
    const ownerId = Number(owner);
    if (Number.isFinite(ownerId) && ownerId > 0) {
      byPlayer.set(ownerId, card);
    }
  }
  if (actorPlayerId > 0 && character) {
    byPlayer.set(actorPlayerId, character);
  }
  return players.map((playerId, index) => ({
    player_id: playerId,
    priority_slot: index + 1,
    character: byPlayer.get(playerId) ?? (playerId === actorPlayerId ? character : null),
    reveal_state: playerId === actorPlayerId ? "revealed" : "selected_private",
    is_current_actor: playerId === actorPlayerId,
  }));
}

function promptHandTray(activePrompt: Record<string, unknown> | null): Array<Record<string, unknown>> {
  const publicContext = isRecord(activePrompt?.public_context) ? activePrompt.public_context : null;
  const fullHand = Array.isArray(publicContext?.full_hand) ? publicContext.full_hand : [];
  return fullHand.filter(isRecord).map((card, index) => ({
    deck_index: numberValue(card.deck_index, index),
    name: stringValue(card.name, stringValue(card.title, `card-${index}`)),
    title: stringValue(card.title, stringValue(card.name, `card-${index}`)),
    description: stringValue(card.description, ""),
    effect: stringValue(card.effect, stringValue(card.description, "")),
    is_hidden: Boolean(card.is_hidden),
  }));
}

function publicTrickHandTray(publicTricks: string[], hiddenTrickCount: number): Array<Record<string, unknown>> {
  const publicCards = publicTricks.map((name, index) => ({
    deck_index: index,
    name,
    title: name,
    description: "",
    effect: "",
    is_hidden: false,
  }));
  const hiddenCards = Array.from({ length: Math.max(0, hiddenTrickCount) }, (_, index) => ({
    deck_index: publicCards.length + index,
    name: "비공개 잔꾀",
    title: "비공개 잔꾀",
    description: "",
    effect: "",
    is_hidden: true,
  }));
  return [...publicCards, ...hiddenCards];
}

function buildCommit(args: {
  sessionId: string;
  manifest: E2EManifestRecord;
  snapshot?: E2ESessionSnapshot;
  source: E2EStreamMessage;
  commitSeq: number;
  roundIndex: number;
  turnIndex: number;
  actorPlayerId: number;
  character: string;
  weatherName: string;
  weatherEffect: string;
  activePrompt: Record<string, unknown> | null;
  activeByCard: Record<string, string>;
  orderedPlayerIds: number[];
  publicTricksByPlayer: Map<number, string[]>;
  hiddenTrickCountByPlayer: Map<number, number>;
  playerPositions: Map<number, number>;
  gameEnded: boolean;
  eventCode: string;
  eventDetail: string;
  currentBeatKind: "move" | "economy" | "effect" | "decision" | "system";
  focusTileIndex: number | null;
  revealItems: RevealItem[];
  coreActionFeed: CoreActionItem[];
  theaterFeed: TheaterItem[];
  timeline: Array<Record<string, unknown>>;
  criticalAlerts: Array<Record<string, unknown>>;
  turnSummaries: TurnSummaries;
  workerStatus: WorkerStatus;
  progressCodes: string[];
  lastMove: LastMove | null;
  baseViewState: Record<string, unknown>;
}): E2EStreamMessage {
  const requestType = stringValue(args.activePrompt?.request_type, "-");
  const moduleType = args.gameEnded ? "GameEndModule" : args.activePrompt ? `${requestType}PromptModule` : "TurnModule";
  const runtimeStatus = args.gameEnded ? "completed" : args.activePrompt ? "waiting_input" : "running";
  const endReason = stringValue(args.source.payload.reason, "");
  const currentBeatDetail = args.gameEnded
    ? endReason
      ? `게임이 종료되었습니다. ${endReason}`
      : "게임이 종료되었습니다."
    : args.activePrompt
      ? stringValue(args.activePrompt.description, "")
      : args.eventDetail;
  const ids = args.orderedPlayerIds.length > 0 ? args.orderedPlayerIds : playerIds(args.manifest, args.snapshot);
  const actorPublicTricks = args.publicTricksByPlayer.get(args.actorPlayerId) ?? [];
  const actorHiddenTrickCount = args.hiddenTrickCountByPlayer.get(args.actorPlayerId) ?? 0;
  const handTrayItems = promptHandTray(args.activePrompt);
  const turnStage = {
    ...(isRecord(args.baseViewState.turn_stage) ? args.baseViewState.turn_stage : {}),
    turn_start_seq: numberValue(args.baseViewState.turn_start_seq, args.source.seq),
    actor_player_id: args.actorPlayerId || null,
    round_index: args.roundIndex,
    turn_index: args.turnIndex,
    character: args.character,
    weather_name: args.weatherName,
    weather_effect: args.weatherEffect,
    current_beat_kind: args.activePrompt ? "decision" : args.currentBeatKind,
    current_beat_event_code: args.gameEnded ? "game_end" : args.activePrompt ? "prompt_active" : args.eventCode,
    current_beat_request_type: requestType,
    current_beat_label: args.gameEnded ? "게임 종료" : args.activePrompt ? stringValue(args.activePrompt.title, requestType) : args.eventCode,
    current_beat_detail: currentBeatDetail,
    current_beat_seq: args.source.seq,
    focus_tile_index: args.focusTileIndex,
    focus_tile_indices: args.focusTileIndex === null ? [] : [args.focusTileIndex],
    prompt_request_type: requestType,
    progress_codes: args.progressCodes,
    ...args.turnSummaries,
    ...args.workerStatus,
  };
  const viewState = {
    ...args.baseViewState,
    schema_version: 1,
    parameter_manifest: args.manifest,
    manifest: args.manifest,
    runtime: {
      runner_kind: "module",
      round_stage: args.gameEnded ? "completed" : "turns",
      turn_stage: args.activePrompt ? "waiting_input" : args.gameEnded ? "completed" : "running",
      latest_module_path: ["RoundModule", "TurnModule", moduleType],
      active_frame_id: `e2e:${args.sessionId}:frame`,
      active_module_id: `e2e:${args.sessionId}:module:${args.commitSeq}`,
      active_module_type: moduleType,
      active_module_status: runtimeStatus,
      active_module_cursor: args.activePrompt ? `${requestType}:await_choice` : "",
      active_prompt_request_id: stringValue(args.activePrompt?.request_id, ""),
      draft_active: requestType === "draft_character",
      trick_sequence_active: requestType.includes("trick"),
      card_flip_legal: false,
    },
    board: {
      topology: args.manifest.board?.topology ?? "ring",
      tile_count: args.manifest.board?.tile_count ?? args.manifest.board?.tiles?.length ?? 0,
      tiles: args.manifest.board?.tiles ?? [],
      marker_owner_player_id: 1,
      marker_draft_direction: "clockwise",
      f_value: 0,
      last_move: args.lastMove,
    },
    players: {
      ordered_player_ids: ids,
      items: ids.map((playerId, index) => ({
        player_id: playerId,
        display_name: `P${playerId}`,
        current_character_face: playerId === args.actorPlayerId ? args.character : null,
        position: args.playerPositions.get(playerId) ?? 0,
        cash: 20,
        burden: 0,
        shards: 4,
        hand_coins: 0,
        placed_coins: 0,
        placed_score_coins: 0,
        score: 0,
        total_score: 0,
        owned_tile_count: 0,
        trick_count: (args.publicTricksByPlayer.get(playerId) ?? []).length + (args.hiddenTrickCountByPlayer.get(playerId) ?? 0),
        public_tricks: args.publicTricksByPlayer.get(playerId) ?? [],
        hidden_trick_count: args.hiddenTrickCountByPlayer.get(playerId) ?? 0,
        priority_slot: index + 1,
        is_marker_owner: playerId === 1,
        is_current_actor: !args.gameEnded && playerId === args.actorPlayerId,
      })),
    },
    player_cards: {
      items: playerCards(ids, args.activeByCard, args.actorPlayerId, args.character),
    },
    active_slots: {
      items: activeCharacterSlots(args.activeByCard, args.character),
    },
    active_by_card: args.activeByCard,
    prompt: {
      active: args.activePrompt,
    },
    hand_tray: {
      items: handTrayItems.length > 0 ? handTrayItems : publicTrickHandTray(actorPublicTricks, actorHiddenTrickCount),
    },
    turn_stage: turnStage,
    scene: {
      situation: {
        actor_player_id: args.actorPlayerId || null,
        headline_seq: args.source.seq,
        headline_message_type: "view_commit",
        headline_event_code: turnStage.current_beat_event_code,
        round_index: args.roundIndex,
        turn_index: args.turnIndex,
        weather_name: args.weatherName,
        weather_effect: args.weatherEffect,
      },
      theater_feed: args.theaterFeed,
      core_action_feed: args.coreActionFeed,
      timeline: args.timeline,
      critical_alerts: args.criticalAlerts,
    },
    reveals: {
      items: args.revealItems,
    },
  };
  return {
    type: "view_commit",
    seq: args.source.seq * 10 + 1,
    session_id: args.sessionId,
    server_time_ms: args.source.server_time_ms + 1,
    delay_ms: typeof args.source.delay_ms === "number" ? args.source.delay_ms + 1 : undefined,
    payload: {
      schema_version: 1,
      commit_seq: args.commitSeq,
      source_event_seq: args.source.seq,
      viewer: { role: "seat", player_id: 1, seat: 1 },
      runtime: {
        status: runtimeStatus,
        round_index: args.roundIndex,
        turn_index: args.turnIndex,
        active_frame_id: `e2e:${args.sessionId}:frame`,
        active_module_id: `e2e:${args.sessionId}:module:${args.commitSeq}`,
        active_module_type: moduleType,
        module_path: ["RoundModule", "TurnModule", moduleType],
      },
      view_state: viewState,
    },
  };
}

export function withAuthoritativeViewCommits(args: {
  sessionManifests: Record<string, E2EManifestRecord>;
  sessionEvents: Record<string, E2EStreamMessage[]>;
  createSessionQueue?: E2ESessionSnapshot[];
  startedSessions?: Record<string, E2ESessionSnapshot>;
  startingCommitSeq?: number;
}): Record<string, E2EStreamMessage[]> {
  const snapshots = new Map<string, E2ESessionSnapshot>();
  for (const created of args.createSessionQueue ?? []) {
    if (created.session_id) {
      snapshots.set(created.session_id, created);
    }
  }
  for (const [sessionId, started] of Object.entries(args.startedSessions ?? {})) {
    snapshots.set(sessionId, { ...(snapshots.get(sessionId) ?? {}), ...started });
  }

  const result: Record<string, E2EStreamMessage[]> = {};
  for (const [sessionId, messages] of Object.entries(args.sessionEvents)) {
    let manifest = snapshots.get(sessionId)?.parameter_manifest ?? args.sessionManifests[sessionId];
    if (!manifest) {
      result[sessionId] = messages;
      continue;
    }
    let commitSeq = args.startingCommitSeq ?? 0;
    let roundIndex = numberValue(snapshots.get(sessionId)?.round_index, 1);
    let turnIndex = numberValue(snapshots.get(sessionId)?.turn_index, 0);
    let actorPlayerId = 0;
    let character = "-";
    let weatherName = "-";
    let weatherEffect = "-";
    let activePrompt: Record<string, unknown> | null = null;
    let gameEnded = false;
    let eventCode = "session_loaded";
    let baseViewState: Record<string, unknown> = {};
    const activeByCard = { ...(snapshots.get(sessionId)?.initial_active_by_card ?? {}) };
    let orderedPlayerIds = playerIds(manifest, snapshots.get(sessionId));
    const publicTricksByPlayer = new Map<number, string[]>();
    const hiddenTrickCountByPlayer = new Map<number, number>();
    const playerPositions = new Map<number, number>();
    let eventDetailText = "-";
    let currentBeatKind: "move" | "economy" | "effect" | "decision" | "system" = "system";
    let currentFocusTileIndex: number | null = null;
    let revealItems: RevealItem[] = [];
    let coreActionFeed: CoreActionItem[] = [];
    let theaterFeed: TheaterItem[] = [];
    let timeline: Array<Record<string, unknown>> = [];
    let criticalAlerts: Array<Record<string, unknown>> = [];
    let turnSummaries = emptyTurnSummaries();
    let workerStatus = emptyWorkerStatus();
    let progressCodes: string[] = [];
    let lastMove: LastMove | null = null;
    const out: E2EStreamMessage[] = [];

    const appendCommit = (source: E2EStreamMessage): void => {
      commitSeq += 1;
      out.push(
        buildCommit({
          sessionId,
          manifest,
          snapshot: snapshots.get(sessionId),
          source,
          commitSeq,
          roundIndex,
          turnIndex,
          actorPlayerId,
          character,
          weatherName,
          weatherEffect,
          activePrompt,
          activeByCard,
          orderedPlayerIds,
          publicTricksByPlayer,
          hiddenTrickCountByPlayer,
          playerPositions,
          gameEnded,
          eventCode,
          eventDetail: eventDetailText,
          currentBeatKind,
          focusTileIndex: currentFocusTileIndex,
          revealItems,
          coreActionFeed,
          theaterFeed,
          timeline,
          criticalAlerts,
          turnSummaries,
          workerStatus,
          progressCodes,
          lastMove,
          baseViewState,
        }),
      );
    };

    for (const message of messages) {
      if (message.type === "view_commit") {
        commitSeq = Math.max(commitSeq, numberValue(message.payload.commit_seq, commitSeq));
        out.push(message);
        continue;
      }
      const payload = isRecord(message.payload) ? message.payload : {};
      let outboundMessage = message;
      let commitSource = message;
      if (message.type === "prompt") {
        activePrompt = payload;
        actorPlayerId = numberValue(payload.player_id, actorPlayerId);
        eventCode = "prompt_active";
        eventDetailText = optionalString(payload.description) || optionalString(payload.title) || eventCode;
        currentBeatKind = "decision";
        currentFocusTileIndex = focusTileIndex(
          isRecord(payload.public_context) ? payload.public_context : payload,
          eventCode
        );
        turnSummaries.prompt_summary = optionalString(payload.title) || optionalString(payload.request_type) || eventCode;
        workerStatus = mergeWorkerStatus(workerStatus, payload.public_context);
      } else {
        eventCode = stringValue(payload.event_type, message.type);
        if (eventCode === "parameter_manifest" && isRecord(payload.parameter_manifest)) {
          manifest = payload.parameter_manifest as E2EManifestRecord;
        }
        if (typeof payload.round_index === "number") {
          roundIndex = payload.round_index;
        }
        if (typeof payload.turn_index === "number") {
          turnIndex = payload.turn_index;
        }
        if (typeof payload.acting_player_id === "number") {
          actorPlayerId = payload.acting_player_id;
        }
        if (typeof payload.character === "string") {
          character = payload.character;
        }
        if (typeof payload.weather_name === "string") {
          weatherName = payload.weather_name;
          weatherEffect = WEATHER_EFFECT_BY_NAME[weatherName] ?? weatherEffect;
        }
        if (typeof payload.weather_effect === "string" || typeof payload.effect_text === "string") {
          weatherEffect = stringValue(payload.weather_effect, stringValue(payload.effect_text, weatherEffect));
        }
        if (isRecord(payload.active_by_card)) {
          for (const [slot, name] of Object.entries(payload.active_by_card)) {
            if (typeof name === "string") {
              activeByCard[slot] = name;
            }
          }
        }
        if (Array.isArray(payload.order)) {
          const nextOrder = payload.order.filter((value): value is number => typeof value === "number" && value > 0);
          if (nextOrder.length > 0) {
            orderedPlayerIds = nextOrder;
          }
        }
        if (eventCode === "initial_public_tricks" && Array.isArray(payload.players)) {
          for (const rawPlayer of payload.players) {
            if (!isRecord(rawPlayer)) {
              continue;
            }
            const playerId = numberValue(rawPlayer.player, numberValue(rawPlayer.player_id, 0));
            if (playerId <= 0) {
              continue;
            }
            const publicTricks = Array.isArray(rawPlayer.public_tricks)
              ? rawPlayer.public_tricks.filter((item): item is string => typeof item === "string")
              : [];
            publicTricksByPlayer.set(playerId, publicTricks);
            hiddenTrickCountByPlayer.set(playerId, numberValue(rawPlayer.hidden_trick_count, 0));
          }
        }
        if (isRecord(payload.view_state)) {
          baseViewState = payload.view_state;
        }
        if (message.type === "decision_ack" || eventCode === "decision_ack") {
          activePrompt = null;
        }
        if (eventCode === "turn_start") {
          activePrompt = null;
          gameEnded = false;
          turnSummaries = emptyTurnSummaries();
          if (weatherEffect && weatherEffect !== "-") {
            turnSummaries.weather_summary = weatherEffect;
          }
          workerStatus = emptyWorkerStatus();
          progressCodes = [];
          revealItems = [];
          currentFocusTileIndex = null;
        }
        if (eventCode === "engine_transition" && payload.status === "completed") {
          activePrompt = null;
          gameEnded = true;
          eventCode = "game_end";
          commitSource = {
            ...message,
            seq: message.seq * 10,
            payload: {
              ...payload,
              event_type: "game_end",
            },
          };
        }
        if (
          (eventCode === "mark_resolved" || eventCode === "mark_queued") &&
          !optionalString(payload.effect_character_name) &&
          optionalString(payload.actor_name)
        ) {
          outboundMessage = {
            ...message,
            payload: {
              ...payload,
              effect_character_name: optionalString(payload.actor_name),
            },
          };
          if (commitSource === message) {
            commitSource = outboundMessage;
          }
        }
        eventDetailText = eventDetail(eventCode, isRecord(commitSource.payload) ? commitSource.payload : payload);
        currentBeatKind = turnBeatKind(eventCode);
        const nextFocusTileIndex = focusTileIndex(payload, eventCode);
        const preserveExistingFocus =
          nextFocusTileIndex === null &&
          (eventCode === "fortune_drawn" ||
            eventCode === "fortune_resolved" ||
            eventCode === "trick_used" ||
            eventCode === "mark_resolved" ||
            eventCode === "mark_queued");
        currentFocusTileIndex = nextFocusTileIndex ?? (preserveExistingFocus ? currentFocusTileIndex : null);
        if (currentFocusTileIndex !== null) {
          const positionedPlayerId = payloadActor(payload, actorPlayerId);
          if (positionedPlayerId > 0) {
            playerPositions.set(positionedPlayerId, currentFocusTileIndex);
          }
        }
        workerStatus = mergeWorkerStatus(workerStatus, payload.public_context);
        updateTurnSummaries(turnSummaries, eventCode, eventDetailText);
        if (eventCode !== "parameter_manifest") {
          progressCodes = [...progressCodes, eventCode].slice(-16);
        }
        if (eventCode === "player_move") {
          lastMove = {
            player_id: payloadActor(payload, actorPlayerId) || null,
            from_tile_index: numberOrNull(payload.from_tile_index ?? payload.from_tile ?? payload.from_pos),
            to_tile_index: numberOrNull(payload.to_tile_index ?? payload.to_tile ?? payload.to_pos),
            path_tile_indices: sourcePath(payload),
          };
        }
        if (REVEAL_EVENT_CODES.has(eventCode) || eventCode === "decision_timeout_fallback") {
          const revealItem: RevealItem = {
            seq: commitSource.seq,
            event_code: eventCode,
            label: eventLabel(eventCode),
            detail: eventDetailText,
            tone: revealTone(eventCode),
            focus_tile_index: currentFocusTileIndex,
            is_interrupt: isInterruptEvent(eventCode),
            effect_character: effectCharacterName(isRecord(commitSource.payload) ? commitSource.payload : payload) || undefined,
          };
          revealItems = [...revealItems, revealItem].slice(-24);
        }
        if (CORE_EVENT_CODES.has(eventCode) || eventCode === "decision_timeout_fallback") {
          const actorId = payloadActor(payload, actorPlayerId);
          const coreItem: CoreActionItem = {
            seq: commitSource.seq,
            event_code: eventCode,
            actor_player_id: actorId > 0 ? actorId : null,
            round_index: roundIndex,
            turn_index: turnIndex,
            detail: eventDetailText,
          };
          coreActionFeed = [coreItem, ...coreActionFeed].slice(0, 32);
          theaterFeed = [
            {
              ...coreItem,
              message_type: "event",
              tone: theaterTone(eventCode),
              lane:
                eventCode === "decision_timeout_fallback" ||
                eventCode === "decision_requested" ||
                eventCode === "decision_resolved"
                  ? "prompt"
                  : "core",
            },
            ...theaterFeed,
          ].slice(0, 40);
          timeline = [
            { seq: commitSource.seq, message_type: "event", event_code: eventCode },
            ...timeline,
          ].slice(0, 40);
        }
        if (eventCode === "decision_timeout_fallback" || eventCode === "bankruptcy" || eventCode === "game_end") {
          criticalAlerts = [
            {
              seq: commitSource.seq,
              message_type: "event",
              event_code: eventCode,
              severity: eventCode === "decision_timeout_fallback" ? "warning" : "critical",
            },
            ...criticalAlerts,
          ].slice(0, 8);
        }
      }
      out.push(outboundMessage);
      if (commitSource !== outboundMessage) {
        out.push(commitSource);
      }
      appendCommit(commitSource);
    }
    if (!out.some((message) => message.type === "view_commit")) {
      appendCommit({
        type: "event",
        seq: 0,
        session_id: sessionId,
        server_time_ms: Date.now(),
        payload: { event_type: "session_loaded" },
      });
    }
    result[sessionId] = out;
  }
  return result;
}

export function latestViewCommit(messages: E2EStreamMessage[] | undefined): E2EStreamMessage | null {
  if (!messages) {
    return null;
  }
  const commits = messages.filter((message) => message.type === "view_commit");
  return commits.length > 0 ? commits.reduce((latest, message) => {
    return numberValue(message.payload.commit_seq, 0) > numberValue(latest.payload.commit_seq, 0) ? message : latest;
  }) : null;
}

export function nextFollowupCommitBase(messages: E2EStreamMessage[] | undefined, fallback = 10_000): number {
  return Math.max(maxCommitSeq(messages ?? []), fallback);
}
