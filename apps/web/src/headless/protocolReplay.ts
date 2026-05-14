import type { HeadlessTraceEvent } from "./HeadlessGameClient";
import type { ProtocolPlayerId } from "../core/contracts/stream";

export type ProtocolReplayIdentitySource = "public" | "protocol" | "legacy";

export type ProtocolReplayLegalAction = {
  action_id: string;
  legal: true;
  label: string;
};

export type ProtocolReplayPlayerSummary = {
  player_id: number;
  primary_player_id: ProtocolPlayerId | null;
  primary_player_id_source: ProtocolReplayIdentitySource | null;
  legacy_player_id: number | null;
  public_player_id: string | null;
  seat_id: string | null;
  viewer_id: string | null;
  cash: number | null;
  score: number | null;
  total_score: number | null;
  shards: number | null;
  owned_tile_count: number | null;
  position: number | null;
  alive: boolean | null;
  character: string | null;
};

export type ProtocolReplayRewardComponents = {
  cash_delta: number;
  shard_delta: number;
  score_delta: number;
  total_score_delta: number;
  tile_delta: number;
  low_cash_risk: number;
  cash_death_risk: number;
  bankruptcy: number;
};

export type ProtocolReplayRow = {
  game_id: string;
  step: number;
  seed: number | null;
  policy_mode: string;
  player_id: number;
  primary_player_id: ProtocolPlayerId | null;
  primary_player_id_source: ProtocolReplayIdentitySource | null;
  legacy_player_id: number | null;
  public_player_id: string | null;
  seat_id: string | null;
  viewer_id: string | null;
  decision_key: string;
  observation: {
    commit_seq: number | null;
    request_id: string | null;
    round_index: number | null;
    turn_index: number | null;
    player_id: number;
    primary_player_id: ProtocolPlayerId | null;
    primary_player_id_source: ProtocolReplayIdentitySource | null;
    legacy_player_id: number | null;
    public_player_id: string | null;
    seat_id: string | null;
    viewer_id: string | null;
    cash: number | null;
    score: number | null;
    total_score: number | null;
    shards: number | null;
    owned_tile_count: number | null;
    position: number | null;
    alive: boolean | null;
    character: string | null;
  };
  legal_actions: ProtocolReplayLegalAction[];
  chosen_action_id: string;
  action_space_source: "full_stack_protocol_trace";
  reward: {
    total: number;
    components: ProtocolReplayRewardComponents;
  };
  sample_weight: number;
  done: boolean;
  outcome: {
    runtime_status: string | null;
    final_rank: number | null;
    final_player_summary: ProtocolReplayPlayerSummary | null;
  };
};

export type ProtocolReplayOptions = {
  seed?: number | null;
  policyMode?: string;
  runtimeStatus?: string | null;
};

export function protocolTraceEventsToReplayRows(
  events: HeadlessTraceEvent[],
  options: ProtocolReplayOptions = {},
): ProtocolReplayRow[] {
  const runtimeStatus = options.runtimeStatus ?? finalRuntimeStatus(events);
  const snapshots = playerSnapshotsFromEvents(events);
  const finalPlayers = snapshots[snapshots.length - 1]?.players ?? [];
  const rows = events
    .filter((event) => event.event === "decision_sent" || event.event === "decision_retry_sent")
    .map((event, index): ProtocolReplayRow => {
      const requestType = stringValue(event.payload?.["request_type"]) ?? "unknown";
      const legalChoiceIds = stringArrayValue(event.payload?.["legal_choice_ids"]);
      const commitSeq = numberOrNull(event.commit_seq);
      const identity = replayIdentityFromEvent(event);
      const before = playerSummaryForSnapshot(snapshotAtOrBefore(snapshots, commitSeq), event.player_id);
      const after = playerSummaryForSnapshot(snapshotAfter(snapshots, commitSeq) ?? snapshots[snapshots.length - 1], event.player_id);
      const finalPlayer = playerSummaryForSnapshot({ commitSeq: null, players: finalPlayers }, event.player_id);
      const observationPlayer = before ?? after ?? finalPlayer;
      return {
        game_id: event.session_id,
        step: index,
        seed: options.seed ?? null,
        policy_mode: options.policyMode ?? "full_stack_protocol",
        player_id: event.player_id,
        primary_player_id: identity.primaryPlayerId,
        primary_player_id_source: identity.primaryPlayerIdSource,
        legacy_player_id: identity.legacyPlayerId,
        public_player_id: identity.publicPlayerId,
        seat_id: identity.seatId,
        viewer_id: identity.viewerId,
        decision_key: requestType,
        observation: {
          commit_seq: numberOrNull(event.commit_seq),
          request_id: stringValue(event.request_id) ?? null,
          round_index: numberOrNull(event.payload?.["round_index"]),
          turn_index: numberOrNull(event.payload?.["turn_index"]),
          player_id: event.player_id,
          primary_player_id: observationPlayer?.primary_player_id ?? identity.primaryPlayerId,
          primary_player_id_source: observationPlayer?.primary_player_id_source ?? identity.primaryPlayerIdSource,
          legacy_player_id: observationPlayer?.legacy_player_id ?? identity.legacyPlayerId,
          public_player_id: observationPlayer?.public_player_id ?? identity.publicPlayerId,
          seat_id: observationPlayer?.seat_id ?? identity.seatId,
          viewer_id: observationPlayer?.viewer_id ?? identity.viewerId,
          cash: observationPlayer?.cash ?? null,
          score: observationPlayer?.score ?? null,
          total_score: observationPlayer?.total_score ?? null,
          shards: observationPlayer?.shards ?? null,
          owned_tile_count: observationPlayer?.owned_tile_count ?? null,
          position: observationPlayer?.position ?? null,
          alive: observationPlayer?.alive ?? null,
          character: observationPlayer?.character ?? null,
        },
        legal_actions: legalChoiceIds.map((choiceId) => ({
          action_id: choiceId,
          legal: true,
          label: choiceId,
        })),
        chosen_action_id: stringValue(event.choice_id) ?? "",
        action_space_source: "full_stack_protocol_trace",
        reward: computeAuthoritativeReward(before, after),
        sample_weight: 1,
        done: false,
        outcome: {
          runtime_status: runtimeStatus,
          final_rank: computeFinalRank(event.player_id, finalPlayers),
          final_player_summary: finalPlayer,
        },
      };
    });
  if (rows.length > 0) {
    rows[rows.length - 1] = {
      ...rows[rows.length - 1],
      done: true,
    };
  }
  return rows;
}

export function serializeProtocolReplayRows(rows: ProtocolReplayRow[]): string {
  return rows.map((row) => JSON.stringify(row)).join("\n");
}

function finalRuntimeStatus(events: HeadlessTraceEvent[]): string | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const status = stringValue(events[index].payload?.["runtime_status"]);
    if (status !== null) {
      return status;
    }
  }
  return null;
}

type PlayerSnapshot = {
  commitSeq: number | null;
  players: ProtocolReplayPlayerSummary[];
};

function playerSnapshotsFromEvents(events: HeadlessTraceEvent[]): PlayerSnapshot[] {
  const byCommitSeq = new Map<number, ProtocolReplayPlayerSummary[]>();
  for (const event of events) {
    if (event.event !== "view_commit_seen") {
      continue;
    }
    const commitSeq = numberOrNull(event.commit_seq);
    if (commitSeq === null) {
      continue;
    }
    const players = playerSummariesFromValue(event.payload?.["player_summaries"]);
    if (players.length <= 0) {
      continue;
    }
    byCommitSeq.set(commitSeq, players);
  }
  return Array.from(byCommitSeq.entries())
    .sort(([left], [right]) => left - right)
    .map(([commitSeq, players]) => ({ commitSeq, players }));
}

function snapshotAtOrBefore(snapshots: PlayerSnapshot[], commitSeq: number | null): PlayerSnapshot | null {
  if (commitSeq === null) {
    return null;
  }
  let candidate: PlayerSnapshot | null = null;
  for (const snapshot of snapshots) {
    if (snapshot.commitSeq === null || snapshot.commitSeq > commitSeq) {
      break;
    }
    candidate = snapshot;
  }
  return candidate;
}

function snapshotAfter(snapshots: PlayerSnapshot[], commitSeq: number | null): PlayerSnapshot | null {
  if (commitSeq === null) {
    return null;
  }
  return snapshots.find((snapshot) => snapshot.commitSeq !== null && snapshot.commitSeq > commitSeq) ?? null;
}

function playerSummaryForSnapshot(
  snapshot: PlayerSnapshot | null | undefined,
  playerId: number,
): ProtocolReplayPlayerSummary | null {
  return snapshot?.players.find((player) => player.player_id === playerId) ?? null;
}

function playerSummariesFromValue(value: unknown): ProtocolReplayPlayerSummary[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .map((item): ProtocolReplayPlayerSummary | null => {
      const playerId = numberOrNull(item["player_id"]);
      if (playerId === null) {
        return null;
      }
      return {
        player_id: playerId,
        ...replayIdentityFieldsFromRecord(item, playerId),
        legacy_player_id: numberOrNull(item["legacy_player_id"]) ?? playerId,
        public_player_id: stringValue(item["public_player_id"]),
        seat_id: stringValue(item["seat_id"]),
        viewer_id: stringValue(item["viewer_id"]),
        cash: numberOrNull(item["cash"]),
        score: numberOrNull(item["score"]),
        total_score: numberOrNull(item["total_score"]),
        shards: numberOrNull(item["shards"]),
        owned_tile_count: numberOrNull(item["owned_tile_count"]),
        position: numberOrNull(item["position"]),
        alive: typeof item["alive"] === "boolean" ? item["alive"] : null,
        character: stringValue(item["character"]),
      };
    })
    .filter((item): item is ProtocolReplayPlayerSummary => item !== null);
}

function replayIdentityFromEvent(event: HeadlessTraceEvent): {
  primaryPlayerId: ProtocolPlayerId | null;
  primaryPlayerIdSource: ProtocolReplayIdentitySource | null;
  legacyPlayerId: number | null;
  publicPlayerId: string | null;
  seatId: string | null;
  viewerId: string | null;
} {
  const record = replayIdentityRecordFromEvent(event);
  const legacyPlayerId = numberOrNull(record["legacy_player_id"]) ?? event.player_id;
  const identity = replayIdentityFieldsFromRecord(record, legacyPlayerId);
  return {
    primaryPlayerId: identity.primary_player_id,
    primaryPlayerIdSource: identity.primary_player_id_source,
    legacyPlayerId,
    publicPlayerId: stringValue(record["public_player_id"]),
    seatId: stringValue(record["seat_id"]),
    viewerId: stringValue(record["viewer_id"]),
  };
}

function replayIdentityRecordFromEvent(event: HeadlessTraceEvent): Record<string, unknown> {
  return {
    ...(event.payload ?? {}),
    primary_player_id: event.primary_player_id ?? event.payload?.["primary_player_id"],
    primary_player_id_source: event.primary_player_id_source ?? event.payload?.["primary_player_id_source"],
    protocol_player_id: event.protocol_player_id ?? event.payload?.["protocol_player_id"],
    legacy_player_id: event.legacy_player_id ?? event.payload?.["legacy_player_id"],
    public_player_id: event.public_player_id ?? event.payload?.["public_player_id"],
    seat_id: event.seat_id ?? event.payload?.["seat_id"],
    viewer_id: event.viewer_id ?? event.payload?.["viewer_id"],
  };
}

function replayIdentityFieldsFromRecord(
  record: Record<string, unknown> | undefined,
  fallbackLegacyPlayerId: number | null,
): Pick<ProtocolReplayPlayerSummary, "primary_player_id" | "primary_player_id_source"> {
  const explicitPrimary = protocolPlayerIdValue(record?.["primary_player_id"]);
  if (explicitPrimary !== null) {
    return {
      primary_player_id: explicitPrimary,
      primary_player_id_source: protocolIdentitySourceValue(record?.["primary_player_id_source"], explicitPrimary),
    };
  }

  const publicPlayerId = stringValue(record?.["public_player_id"]);
  if (publicPlayerId !== null) {
    return {
      primary_player_id: publicPlayerId,
      primary_player_id_source: "public",
    };
  }

  const protocolPlayerId = protocolPlayerIdValue(record?.["protocol_player_id"]);
  if (protocolPlayerId !== null) {
    return {
      primary_player_id: protocolPlayerId,
      primary_player_id_source: "protocol",
    };
  }

  return {
    primary_player_id: fallbackLegacyPlayerId,
    primary_player_id_source: fallbackLegacyPlayerId === null ? null : "legacy",
  };
}

function computeAuthoritativeReward(
  before: ProtocolReplayPlayerSummary | null,
  after: ProtocolReplayPlayerSummary | null,
): ProtocolReplayRow["reward"] {
  const cashDelta = numericDelta(before?.cash, after?.cash);
  const shardDelta = numericDelta(before?.shards, after?.shards);
  const scoreDelta = numericDelta(before?.score, after?.score);
  const totalScoreDelta = numericDelta(before?.total_score, after?.total_score);
  const tileDelta = numericDelta(before?.owned_tile_count, after?.owned_tile_count);
  const cashAfter = after?.cash;
  const lowCashRisk =
    cashAfter === null || cashAfter === undefined || cashAfter <= 0
      ? 0
      : cashAfter < 5
        ? -((5 - cashAfter) / 5)
        : 0;
  const cashDeathRisk = cashAfter !== null && cashAfter !== undefined && cashAfter <= 0 ? -2 : 0;
  const bankruptcy = before?.alive !== false && after?.alive === false ? -4 : 0;
  const totalRaw =
    cashDelta / 5 +
    shardDelta * 0.4 +
    scoreDelta * 0.6 +
    totalScoreDelta * 0.2 +
    tileDelta * 0.25 +
    lowCashRisk +
    cashDeathRisk +
    bankruptcy;
  return {
    total: clamp(round(totalRaw), -4, 3),
    components: {
      cash_delta: round(cashDelta),
      shard_delta: round(shardDelta),
      score_delta: round(scoreDelta),
      total_score_delta: round(totalScoreDelta),
      tile_delta: round(tileDelta),
      low_cash_risk: round(lowCashRisk),
      cash_death_risk: round(cashDeathRisk),
      bankruptcy: round(bankruptcy),
    },
  };
}

function numericDelta(before: number | null | undefined, after: number | null | undefined): number {
  if (before === null || before === undefined || after === null || after === undefined) {
    return 0;
  }
  return after - before;
}

function computeFinalRank(playerId: number, players: ProtocolReplayPlayerSummary[]): number | null {
  if (players.length <= 0 || !players.some((player) => player.player_id === playerId)) {
    return null;
  }
  const ranked = [...players].sort(comparePlayerOutcome);
  return ranked.findIndex((player) => player.player_id === playerId) + 1;
}

function comparePlayerOutcome(left: ProtocolReplayPlayerSummary, right: ProtocolReplayPlayerSummary): number {
  return (
    compareNumber(right.alive === false ? 0 : 1, left.alive === false ? 0 : 1) ||
    compareNumber(right.total_score ?? right.score ?? 0, left.total_score ?? left.score ?? 0) ||
    compareNumber(right.cash ?? 0, left.cash ?? 0) ||
    compareNumber(right.shards ?? 0, left.shards ?? 0) ||
    compareNumber(right.owned_tile_count ?? 0, left.owned_tile_count ?? 0) ||
    compareNumber(left.player_id, right.player_id)
  );
}

function compareNumber(left: number, right: number): number {
  return left === right ? 0 : left > right ? 1 : -1;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function protocolPlayerIdValue(value: unknown): ProtocolPlayerId | null {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function protocolIdentitySourceValue(
  value: unknown,
  primaryPlayerId: ProtocolPlayerId,
): ProtocolReplayIdentitySource {
  if (value === "public" || value === "protocol" || value === "legacy") {
    return value;
  }
  return typeof primaryPlayerId === "number" ? "legacy" : "protocol";
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function round(value: number): number {
  return Number(value.toFixed(6));
}
