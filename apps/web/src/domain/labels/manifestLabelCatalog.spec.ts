import { describe, expect, it } from "vitest";
import { characterAbilityLabelsFromManifestLabels, tileKindLabelsFromManifestLabels } from "./manifestLabelCatalog";

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

  it("extracts character ability labels from both flat and nested entries", () => {
    expect(
      characterAbilityLabelsFromManifestLabels({
        character_ability_labels: {
          "건설업자": "[효과] 이번 턴 토지 무료 구입",
          "교리 연구관": {
            ability_text: "[액티브] 자신 또는 팀원의 짐 카드 1장을 제거합니다.",
            pair: "교리 감독관",
          },
        },
      })
    ).toEqual({
      "건설업자": "[효과] 이번 턴 토지 무료 구입",
      "교리 연구관": "[액티브] 자신 또는 팀원의 짐 카드 1장을 제거합니다.",
    });
  });

  it("returns empty map for invalid character ability labels payloads", () => {
    expect(characterAbilityLabelsFromManifestLabels(null)).toEqual({});
    expect(characterAbilityLabelsFromManifestLabels([])).toEqual({});
    expect(characterAbilityLabelsFromManifestLabels({ character_ability_labels: [] })).toEqual({});
    expect(characterAbilityLabelsFromManifestLabels({ character_ability_labels: { "건설업자": 123 } })).toEqual({});
  });
});
