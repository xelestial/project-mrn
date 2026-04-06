import { describe, expect, it } from "vitest";
import { KNOWN_PROMPT_TYPES } from "../../domain/labels/promptTypeCatalog";
import { SPECIALIZED_PROMPT_TYPES, isSpecializedPromptType } from "./promptSurfaceCatalog";

describe("promptSurfaceCatalog", () => {
  it("covers every known prompt type with a specialized surface", () => {
    expect(new Set(SPECIALIZED_PROMPT_TYPES)).toEqual(new Set(KNOWN_PROMPT_TYPES));
  });

  it("recognizes known specialized prompt types", () => {
    for (const requestType of KNOWN_PROMPT_TYPES) {
      expect(isSpecializedPromptType(requestType)).toBe(true);
    }
    expect(isSpecializedPromptType("unknown_prompt_type")).toBe(false);
  });
});
