import { describe, expect, it } from "vitest";
import { tileKindLabelsFromManifestLabels } from "./manifestLabelCatalog";

describe("manifestLabelCatalog", () => {
  it("extracts tile kind labels from snake_case field", () => {
    expect(
      tileKindLabelsFromManifestLabels({
        tile_kind_labels: {
          S: "Fortune",
          F1: "End - 1",
        },
      })
    ).toEqual({
      S: "Fortune",
      F1: "End - 1",
    });
  });

  it("extracts tile kind labels from camelCase compatibility field", () => {
    expect(
      tileKindLabelsFromManifestLabels({
        tileKindLabels: {
          T2: "Land",
        },
      })
    ).toEqual({
      T2: "Land",
    });
  });

  it("returns empty map for invalid payloads", () => {
    expect(tileKindLabelsFromManifestLabels(null)).toEqual({});
    expect(tileKindLabelsFromManifestLabels([])).toEqual({});
    expect(tileKindLabelsFromManifestLabels({ tile_kind_labels: [] })).toEqual({});
    expect(tileKindLabelsFromManifestLabels({ tile_kind_labels: { S: 7 } })).toEqual({});
  });
});
