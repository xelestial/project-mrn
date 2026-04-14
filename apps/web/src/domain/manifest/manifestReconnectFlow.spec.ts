import { describe, expect, it } from "vitest";
import { gameStreamReducer, initialGameStreamState } from "../store/gameStreamReducer";
import { selectLatestManifest } from "../selectors/streamSelectors";
import { mergeSessionManifest } from "./manifestRehydrate";

describe("manifest reconnect flow", () => {
  it("rehydrates from latest manifest after hash change during replay", () => {
    let state = initialGameStreamState;

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: {
            manifest_hash: "hash_old",
            board: { topology: "ring", tile_count: 40 },
            seats: { allowed: [1, 2, 3, 4] },
            economy: { starting_cash: 20 },
            resources: { starting_shards: 4 },
            labels: { tile_kind_labels: { S: "운수" } },
          },
        },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: { event_type: "round_start", round_index: 1 },
      },
    });

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: {
            manifest_hash: "hash_new",
            board: {
              topology: "line",
              tiles: [{ tile_index: 0, tile_kind: "F1", zone_color: "", purchase_cost: null, rent_cost: null }],
            },
            seats: { allowed: [1, 2, 3] },
            economy: { starting_cash: 55 },
            resources: { starting_shards: 7 },
            labels: { tile_kind_labels: { S: "운수", F1: "종료 - 1" } },
          },
        },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 4,
        session_id: "s1",
        payload: { event_type: "round_start", round_index: 9 },
      },
    });

    expect(state.messages.map((m) => m.seq)).toEqual([3, 4]);
    expect(state.manifestHash).toBe("hash_new");

    const latest = selectLatestManifest(state.messages);
    expect(latest).not.toBeNull();
    const merged = mergeSessionManifest(null, latest!);
    expect(merged.manifest_hash).toBe("hash_new");
    expect(merged.board?.topology).toBe("line");
    expect(merged.seats?.allowed).toEqual([1, 2, 3]);
    expect(merged.economy?.starting_cash).toBe(55);
    expect(merged.resources?.starting_shards).toBe(7);
    expect(merged.labels).toEqual({
      tile_kind_labels: {
        S: "운수",
        F1: "종료 - 1",
      },
    });
  });
});
