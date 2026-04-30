import minseoBackLeftUrl from "../../assets/characters/sprites/minseo/back-left.png";
import minseoBackRightUrl from "../../assets/characters/sprites/minseo/back-right.png";
import minseoFrontLeftUrl from "../../assets/characters/sprites/minseo/front-left.png";
import minseoFrontRightUrl from "../../assets/characters/sprites/minseo/front-right.png";
import seoyeonBackLeftUrl from "../../assets/characters/sprites/seoyeon/back-left.png";
import seoyeonBackRightUrl from "../../assets/characters/sprites/seoyeon/back-right.png";
import seoyeonFrontLeftUrl from "../../assets/characters/sprites/seoyeon/front-left.png";
import seoyeonFrontRightUrl from "../../assets/characters/sprites/seoyeon/front-right.png";
import suaBackLeftUrl from "../../assets/characters/sprites/sua/back-left.png";
import suaBackRightUrl from "../../assets/characters/sprites/sua/back-right.png";
import suaFrontLeftUrl from "../../assets/characters/sprites/sua/front-left.png";
import suaFrontRightUrl from "../../assets/characters/sprites/sua/front-right.png";
import jiaBackLeftUrl from "../../assets/characters/sprites/jia/back-left.png";
import jiaBackRightUrl from "../../assets/characters/sprites/jia/back-right.png";
import jiaFrontLeftUrl from "../../assets/characters/sprites/jia/front-left.png";
import jiaFrontRightUrl from "../../assets/characters/sprites/jia/front-right.png";
import hayoonBackLeftUrl from "../../assets/characters/sprites/hayoon/back-left.png";
import hayoonBackRightUrl from "../../assets/characters/sprites/hayoon/back-right.png";
import hayoonFrontLeftUrl from "../../assets/characters/sprites/hayoon/front-left.png";
import hayoonFrontRightUrl from "../../assets/characters/sprites/hayoon/front-right.png";

export type CharacterSpriteFacing = "front-right" | "front-left" | "back-right" | "back-left";

export type CharacterSpriteSet = {
  readonly name: string;
  readonly assetKey: string;
  readonly sprites: Record<CharacterSpriteFacing, string>;
};

export const CHARACTER_SPRITE_ROSTER: readonly CharacterSpriteSet[] = [
  {
    name: "민서",
    assetKey: "minseo",
    sprites: {
      "front-right": minseoFrontRightUrl,
      "front-left": minseoFrontLeftUrl,
      "back-right": minseoBackRightUrl,
      "back-left": minseoBackLeftUrl,
    },
  },
  {
    name: "서연",
    assetKey: "seoyeon",
    sprites: {
      "front-right": seoyeonFrontRightUrl,
      "front-left": seoyeonFrontLeftUrl,
      "back-right": seoyeonBackRightUrl,
      "back-left": seoyeonBackLeftUrl,
    },
  },
  {
    name: "수아",
    assetKey: "sua",
    sprites: {
      "front-right": suaFrontRightUrl,
      "front-left": suaFrontLeftUrl,
      "back-right": suaBackRightUrl,
      "back-left": suaBackLeftUrl,
    },
  },
  {
    name: "지아",
    assetKey: "jia",
    sprites: {
      "front-right": jiaFrontRightUrl,
      "front-left": jiaFrontLeftUrl,
      "back-right": jiaBackRightUrl,
      "back-left": jiaBackLeftUrl,
    },
  },
  {
    name: "하윤",
    assetKey: "hayoon",
    sprites: {
      "front-right": hayoonFrontRightUrl,
      "front-left": hayoonFrontLeftUrl,
      "back-right": hayoonBackRightUrl,
      "back-left": hayoonBackLeftUrl,
    },
  },
];

export function characterSpriteSetForPlayer(playerId: number): CharacterSpriteSet {
  const normalizedPlayerId = Number.isFinite(playerId) ? Math.max(1, Math.trunc(playerId)) : 1;
  return CHARACTER_SPRITE_ROSTER[(normalizedPlayerId - 1) % CHARACTER_SPRITE_ROSTER.length];
}

export function characterSpritesForPlayer(playerId: number): Record<CharacterSpriteFacing, string> {
  return characterSpriteSetForPlayer(playerId).sprites;
}
