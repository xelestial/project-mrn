import type { OutboundMessage } from "../../core/contracts/stream";
import type { PromptContinuationViewModel } from "../selectors/promptSelectors";

export function buildGameStreamKey(sessionId: string, token?: string): string {
  return `${sessionId.trim()}\n${token ?? ""}`;
}

const sentDecisionRequestIdsByStreamKey = new Map<string, Set<string>>();

function sentDecisionRequestIdsFor(streamKey: string): Set<string> {
  let sentRequestIds = sentDecisionRequestIdsByStreamKey.get(streamKey);
  if (!sentRequestIds) {
    sentRequestIds = new Set<string>();
    sentDecisionRequestIdsByStreamKey.set(streamKey, sentRequestIds);
  }
  return sentRequestIds;
}

export function createDecisionRequestLedger(): {
  shouldSend: (streamKey: string, requestId: string) => boolean;
  recordSent: (streamKey: string, requestId: string) => void;
  forget: (streamKey: string, requestId: string) => void;
  clear: () => void;
} {
  let activeStreamKey = "";

  const resetIfStreamChanged = (streamKey: string) => {
    if (activeStreamKey === streamKey) {
      return;
    }
    activeStreamKey = streamKey;
  };

  return {
    shouldSend: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      return !sentDecisionRequestIdsFor(streamKey).has(requestId);
    },
    recordSent: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      sentDecisionRequestIdsFor(streamKey).add(requestId);
    },
    forget: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      sentDecisionRequestIdsFor(streamKey).delete(requestId);
    },
    clear: () => {
      activeStreamKey = "";
    },
  };
}

export function buildDecisionMessage(args: {
  requestId: string;
  playerId: number;
  choiceId: string;
  choicePayload?: Record<string, unknown>;
  continuation?: PromptContinuationViewModel;
  viewCommitSeqSeen: number;
  clientSeq: number;
}): OutboundMessage {
  const continuation = args.continuation;
  return {
    type: "decision",
    request_id: args.requestId,
    player_id: args.playerId,
    choice_id: args.choiceId,
    choice_payload: args.choicePayload,
    ...(continuation?.resumeToken ? { resume_token: continuation.resumeToken } : {}),
    ...(continuation?.frameId ? { frame_id: continuation.frameId } : {}),
    ...(continuation?.moduleId ? { module_id: continuation.moduleId } : {}),
    ...(continuation?.moduleType ? { module_type: continuation.moduleType } : {}),
    ...(continuation?.moduleCursor ? { module_cursor: continuation.moduleCursor } : {}),
    ...(continuation?.batchId ? { batch_id: continuation.batchId } : {}),
    ...(continuation?.missingPlayerIds ? { missing_player_ids: continuation.missingPlayerIds } : {}),
    ...(continuation?.resumeTokensByPlayerId
      ? { resume_tokens_by_player_id: continuation.resumeTokensByPlayerId }
      : {}),
    ...(typeof continuation?.promptInstanceId === "number" &&
    Number.isFinite(continuation.promptInstanceId) &&
    continuation.promptInstanceId >= 0
      ? { prompt_instance_id: continuation.promptInstanceId }
      : {}),
    view_commit_seq_seen: Math.max(0, Math.floor(args.viewCommitSeqSeen)),
    client_seq: args.clientSeq,
  };
}
