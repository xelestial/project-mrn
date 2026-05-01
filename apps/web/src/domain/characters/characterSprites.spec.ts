import { describe, expect, it } from "vitest";
import { CHARACTER_SPRITE_ROSTER, characterSpriteSetForPlayer } from "./characterSprites";

describe("character sprite roster", () => {
  it("uses the named character sprite directories as the canonical roster", () => {
    expect(CHARACTER_SPRITE_ROSTER.map((character) => character.assetKey)).toEqual(["minseo", "seoyeon", "sua", "jia", "hayoon"]);
  });

  it("assigns stable named characters to player slots", () => {
    expect(characterSpriteSetForPlayer(1).name).toBe("민서");
    expect(characterSpriteSetForPlayer(2).name).toBe("서연");
    expect(characterSpriteSetForPlayer(3).name).toBe("수아");
    expect(characterSpriteSetForPlayer(4).name).toBe("지아");
  });

  it("provides real directional art for every board facing", () => {
    const minseo = characterSpriteSetForPlayer(1);

    expect(Object.keys(minseo.sprites).sort()).toEqual(["back-left", "back-right", "front-left", "front-right"]);
    expect(minseo.sprites["front-right"]).toContain("front-right.png");
    expect(minseo.sprites["front-left"]).toContain("front-left.png");
    expect(minseo.sprites["back-right"]).toContain("back-right.png");
    expect(minseo.sprites["back-left"]).toContain("back-left.png");
  });

  it("adds the 10-frame walking sheets only to Minseo", () => {
    const minseo = characterSpriteSetForPlayer(1);

    expect(Object.keys(minseo.walkSprites ?? {}).sort()).toEqual(["back-left", "back-right", "front-left", "front-right"]);
    expect(minseo.walkSprites?.["front-right"]?.url).toContain("walk-front-right-videoref-10f.png");
    expect(minseo.walkSprites?.["front-right"]?.frameCount).toBe(10);
    expect(minseo.walkSprites?.["front-right"]?.frameWidth).toBe(180);
    expect(minseo.walkSprites?.["front-right"]?.frameHeight).toBe(270);
    expect(minseo.walkSprites?.["front-right"]?.frameStepMs).toBe(160);
    expect(characterSpriteSetForPlayer(2).walkSprites).toBeUndefined();
  });
});
