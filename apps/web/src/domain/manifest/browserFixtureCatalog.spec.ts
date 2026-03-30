import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type BrowserFixture = {
  id: string;
  title: string;
  goal: string;
  assertions: string[];
};

function loadFixture(name: string): BrowserFixture {
  const path = resolve(process.cwd(), "e2e", "fixtures", name);
  const raw = readFileSync(path, "utf-8");
  return JSON.parse(raw) as BrowserFixture;
}

describe("browser fixture catalog", () => {
  it("includes non-default topology fixture with required assertions", () => {
    const fixture = loadFixture("non_default_topology_line_3seat.json");
    expect(fixture.id).toBe("non_default_topology_line_3seat");
    expect(fixture.assertions.length).toBeGreaterThanOrEqual(3);
  });

  it("includes manifest hash reconnect fixture with required assertions", () => {
    const fixture = loadFixture("manifest_hash_reconnect.json");
    expect(fixture.id).toBe("manifest_hash_reconnect");
    expect(fixture.assertions.length).toBeGreaterThanOrEqual(3);
  });

  it("includes parameter matrix fixture with required assertions", () => {
    const fixture = loadFixture("parameter_matrix_economy_dice_2seat.json");
    expect(fixture.id).toBe("parameter_matrix_economy_dice_2seat");
    expect(fixture.assertions.length).toBeGreaterThanOrEqual(3);
  });
});
