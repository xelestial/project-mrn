export function createScreenProgressGuard(options: {
  stallMs: number;
  startTimeMs?: number;
}): {
  observe(snapshot: {
    nowMs: number;
    commitSeq: number;
    screenSignature: string;
  }): {
    status: "progress" | "idle" | "stalled";
    stalledMs?: number;
    lastCommitSeq?: number;
  };
};
