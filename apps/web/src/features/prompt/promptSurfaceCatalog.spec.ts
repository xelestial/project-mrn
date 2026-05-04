import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { KNOWN_PROMPT_TYPES } from "../../domain/labels/promptTypeCatalog";
import { SPECIALIZED_PROMPT_TYPES, isSpecializedPromptType } from "./promptSurfaceCatalog";

const currentDir = dirname(fileURLToPath(import.meta.url));

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

  it("keeps backend-owned prompt surface values out of public_context fallbacks", () => {
    const source = readFileSync(resolve(currentDir, "PromptOverlay.tsx"), "utf8");

    expect(source).not.toContain('prompt.surface.lapReward?.budget ?? numberFromContext(prompt.publicContext, "budget")');
    expect(source).not.toContain('prompt.surface.doctrineRelief?.candidateCount ?? numberFromContext(prompt.publicContext, "candidate_count")');
    expect(source).not.toContain('prompt.surface.trickTileTarget?.candidateTiles.length ?? numberFromContext(prompt.publicContext, "candidate_count")');
    expect(source).not.toContain("prompt.surface.coinPlacement?.ownedTileCount ?? ownedTileIndices.length");
    expect(source).not.toContain('prompt.surface.characterPick?.draftPhase ?? numberFromContext(prompt.publicContext, "draft_phase")');
    expect(source).not.toContain('prompt.surface.characterPick?.choiceCount ?? numberFromContext(prompt.publicContext, "offered_count")');
    expect(source).not.toContain("numberFromNestedContext(prompt.publicContext");
  });
});
