const DEFAULT_STALL_MS = 60_000;

function normalizedCommitSeq(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? Math.trunc(numeric) : 0;
}

function normalizedSignature(value) {
  return typeof value === "string" ? value : "";
}

export function createScreenProgressGuard(options = {}) {
  const stallMs = Number.isFinite(Number(options.stallMs)) ? Math.max(1, Number(options.stallMs)) : DEFAULT_STALL_MS;
  let lastProgressAtMs = Number.isFinite(Number(options.startTimeMs)) ? Number(options.startTimeMs) : Date.now();
  let lastCommitSeq = normalizedCommitSeq(options.initialCommitSeq);
  let lastScreenSignature = normalizedSignature(options.initialScreenSignature);

  function observe(sample) {
    const nowMs = Number.isFinite(Number(sample?.nowMs)) ? Number(sample.nowMs) : Date.now();
    const commitSeq = normalizedCommitSeq(sample?.commitSeq);
    const screenSignature = normalizedSignature(sample?.screenSignature);
    const screenChanged = screenSignature.length > 0 && screenSignature !== lastScreenSignature;
    if (commitSeq > lastCommitSeq) {
      lastCommitSeq = commitSeq;
    }

    if (screenChanged) {
      lastProgressAtMs = nowMs;
      lastScreenSignature = screenSignature || lastScreenSignature;
      return {
        status: "progress",
        stalledMs: 0,
        lastProgressAtMs,
        lastCommitSeq,
        reason: "screen_signature_changed",
      };
    }

    const stalledMs = Math.max(0, nowMs - lastProgressAtMs);
    if (stalledMs >= stallMs) {
      return {
        status: "stalled",
        stalledMs,
        lastProgressAtMs,
        lastCommitSeq,
        reason: "screen_update_stalled",
      };
    }

    return {
      status: "idle",
      stalledMs,
      lastProgressAtMs,
      lastCommitSeq,
      reason: "waiting_for_screen_update",
    };
  }

  return {
    observe,
    get lastCommitSeq() {
      return lastCommitSeq;
    },
    get lastProgressAtMs() {
      return lastProgressAtMs;
    },
  };
}
