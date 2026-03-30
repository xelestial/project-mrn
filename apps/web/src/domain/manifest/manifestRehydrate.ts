import type { ParameterManifest } from "../../infra/http/sessionApi";
import type { ParameterManifestViewModel } from "../selectors/streamSelectors";

export function mergeSessionManifest(
  previous: ParameterManifest | null,
  latest: ParameterManifestViewModel
): ParameterManifest {
  if (previous?.manifest_hash === latest.manifestHash) {
    return previous;
  }

  return {
    manifest_version: latest.manifestVersion,
    manifest_hash: latest.manifestHash,
    source_fingerprints: latest.sourceFingerprints,
    version: latest.version,
    board: {
      ...(previous?.board ?? {}),
      topology: latest.boardTopology,
      tiles: latest.boardTiles.map((tile) => ({
        tile_index: tile.tileIndex,
        tile_kind: tile.tileKind,
        zone_color: tile.zoneColor,
        purchase_cost: tile.purchaseCost,
        rent_cost: tile.rentCost,
      })),
    },
    seats: {
      ...(previous?.seats ?? {}),
      allowed: latest.seatAllowed,
    },
    dice: {
      ...(previous?.dice ?? {}),
      values: latest.dice.values ?? previous?.dice?.values,
      max_cards_per_turn: latest.dice.maxCardsPerTurn ?? previous?.dice?.max_cards_per_turn,
      use_one_card_plus_one_die: latest.dice.useOneCardPlusOneDie ?? previous?.dice?.use_one_card_plus_one_die,
    },
    labels: Object.keys(latest.labels).length > 0 ? latest.labels : previous?.labels,
  };
}
