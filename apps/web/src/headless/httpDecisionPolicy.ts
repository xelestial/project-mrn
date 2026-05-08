import type { ViewCommitPayload } from "../core/contracts/stream";
import type { PromptChoiceViewModel } from "../domain/selectors/promptSelectors";
import type { DecisionPolicy, HeadlessDecisionContext, HeadlessPolicyDecision } from "./HeadlessGameClient";

export type HttpDecisionPolicyOptions = {
  endpoint: string;
  timeoutMs?: number;
  headers?: Record<string, string>;
};

export type HttpDecisionPolicyRequest = {
  protocol_version: 1;
  session_id: string;
  player_id: number;
  commit_seq: number;
  runtime: {
    status: string | null;
    round_index: number | null;
    turn_index: number | null;
    active_module_type: string | null;
  };
  prompt: {
    request_id: string;
    request_type: string;
    prompt_instance_id: number | null;
    module_type: string | null;
    public_context: Record<string, unknown>;
  };
  legal_choices: Array<{
    choice_id: string;
    title: string;
    description: string;
    secondary: boolean;
    value: Record<string, unknown> | null;
  }>;
  player_summary: Record<string, unknown> | null;
};

type HttpDecisionPolicyResponse = {
  choice_id?: unknown;
  choiceId?: unknown;
  choice_payload?: unknown;
  choicePayload?: unknown;
};

const DEFAULT_HTTP_POLICY_TIMEOUT_MS = 2_000;

export function createHttpDecisionPolicy(options: HttpDecisionPolicyOptions): DecisionPolicy {
  const endpoint = options.endpoint.trim();
  if (!endpoint) {
    throw new Error("HTTP decision policy requires a non-empty endpoint.");
  }
  const timeoutMs =
    typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs)
      ? Math.max(1, Math.floor(options.timeoutMs))
      : DEFAULT_HTTP_POLICY_TIMEOUT_MS;

  return async (context) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(options.headers ?? {}),
        },
        body: JSON.stringify(buildHttpDecisionPolicyRequest(context)),
        signal: controller.signal,
      });
      const body = (await response.json().catch(() => ({}))) as HttpDecisionPolicyResponse;
      if (!response.ok) {
        throw new Error(`HTTP decision policy failed (${response.status}): ${JSON.stringify(body)}`);
      }
      return parseHttpDecisionPolicyResponse(body);
    } finally {
      clearTimeout(timeout);
    }
  };
}

export function buildHttpDecisionPolicyRequest(context: HeadlessDecisionContext): HttpDecisionPolicyRequest {
  const runtime = context.latestCommit?.runtime;
  return {
    protocol_version: 1,
    session_id: context.sessionId,
    player_id: context.playerId,
    commit_seq: context.lastCommitSeq,
    runtime: {
      status: runtime?.status ?? null,
      round_index: runtime?.round_index ?? null,
      turn_index: runtime?.turn_index ?? null,
      active_module_type: runtime?.active_module_type ?? null,
    },
    prompt: {
      request_id: context.prompt.requestId,
      request_type: context.prompt.requestType,
      prompt_instance_id: context.prompt.continuation.promptInstanceId,
      module_type: context.prompt.continuation.moduleType,
      public_context: { ...context.prompt.publicContext },
    },
    legal_choices: context.legalChoices.map(compactLegalChoice),
    player_summary: compactPolicyPlayerSummary(context.latestCommit, context.playerId),
  };
}

function compactLegalChoice(choice: PromptChoiceViewModel): HttpDecisionPolicyRequest["legal_choices"][number] {
  return {
    choice_id: choice.choiceId,
    title: choice.title,
    description: choice.description,
    secondary: choice.secondary,
    value: choice.value,
  };
}

function parseHttpDecisionPolicyResponse(body: HttpDecisionPolicyResponse): HeadlessPolicyDecision {
  const choiceId = stringValue(body.choice_id) ?? stringValue(body.choiceId);
  if (!choiceId) {
    throw new Error("HTTP decision policy response did not include choice_id.");
  }
  const payload = isRecord(body.choice_payload)
    ? body.choice_payload
    : isRecord(body.choicePayload)
      ? body.choicePayload
      : undefined;
  return {
    choiceId,
    choicePayload: payload,
  };
}

function compactPolicyPlayerSummary(
  latestCommit: ViewCommitPayload | null,
  playerId: number,
): Record<string, unknown> | null {
  const viewState = latestCommit?.view_state;
  if (!isRecord(viewState)) {
    return null;
  }
  const players = isRecord(viewState["players"]) ? viewState["players"] : null;
  const items = Array.isArray(players?.["items"]) ? players["items"] : [];
  const player = items.find(
    (item): item is Record<string, unknown> =>
      isRecord(item) && numberValue(item["player_id"]) === playerId,
  );
  if (!player) {
    return null;
  }
  return {
    player_id: numberValue(player["player_id"]),
    cash: numberValue(player["cash"]),
    score: numberValue(player["score"]),
    total_score: numberValue(player["total_score"]),
    shards: numberValue(player["shards"]),
    owned_tile_count: numberValue(player["owned_tile_count"]),
    position: numberValue(player["position"]),
    alive: booleanValue(player["alive"]),
    character: stringValue(player["current_character_face"]) ?? stringValue(player["character"]),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}
