import { describe, expect, it } from "vitest";
import type { ParameterManifest } from "../../infra/http/sessionApi";
import type { ParameterManifestViewModel } from "../selectors/streamSelectors";
import { mergeSessionManifest } from "./manifestRehydrate";

function createLatest(overrides?: Partial<ParameterManifestViewModel>): ParameterManifestViewModel {
  return {
    manifestHash: "hash_latest",
    manifestVersion: 3,
    version: "v3",
    sourceFingerprints: { ruleset: "new" },
    boardTopology: "line",
    boardTiles: [
      {
        tileIndex: 0,
        tileKind: "F1",
        zoneColor: "",
        purchaseCost: null,
        rentCost: null,
        scoreCoinCount: 0,
        ownerPlayerId: null,
        pawnPlayerIds: [],
      },
    ],
    seatAllowed: [1, 2, 3],
    labels: {
      tile_kind_labels: {
        F1: "End - 1",
        S: "Fortune",
      },
    },
    dice: {
      values: [1, 2, 3, 4, 5, 6],
      maxCardsPerTurn: 2,
      useOneCardPlusOneDie: true,
    },
    ...overrides,
  };
}

describe("mergeSessionManifest", () => {
  it("merges latest topology, seats, tiles, labels, and fingerprint fields", () => {
    const previous: ParameterManifest = {
      manifest_version: 2,
      manifest_hash: "old_hash",
      source_fingerprints: { ruleset: "old" },
      version: "v2",
      board: {
        topology: "ring",
        tile_count: 40,
        tiles: [],
      },
      seats: {
        min: 1,
        max: 4,
        allowed: [1, 2, 3, 4],
      },
      labels: {
        tile_kind_labels: {
          F1: "old",
        },
      },
    };

    const merged = mergeSessionManifest(previous, createLatest());

    expect(merged.manifest_hash).toBe("hash_latest");
    expect(merged.manifest_version).toBe(3);
    expect(merged.version).toBe("v3");
    expect(merged.source_fingerprints).toEqual({ ruleset: "new" });
    expect(merged.board?.topology).toBe("line");
    expect(merged.board?.tiles?.[0]?.tile_kind).toBe("F1");
    expect(merged.seats?.allowed).toEqual([1, 2, 3]);
    expect(merged.labels).toEqual({
      tile_kind_labels: {
        F1: "End - 1",
        S: "Fortune",
      },
    });
  });

  it("keeps previous labels when latest labels are empty", () => {
    const previous: ParameterManifest = {
      manifest_version: 1,
      manifest_hash: "old_hash",
      source_fingerprints: {},
      version: "v1",
      labels: {
        tile_kind_labels: {
          T2: "Land",
        },
      },
    };

    const merged = mergeSessionManifest(previous, createLatest({ labels: {} }));
    expect(merged.labels).toEqual({
      tile_kind_labels: {
        T2: "Land",
      },
    });
  });

  it("returns previous reference when manifest hash is unchanged", () => {
    const previous: ParameterManifest = {
      manifest_version: 1,
      manifest_hash: "hash_same",
      source_fingerprints: {},
      version: "v1",
    };

    const merged = mergeSessionManifest(previous, createLatest({ manifestHash: "hash_same" }));
    expect(merged).toBe(previous);
  });
});
