import { describe, expect, it } from "vitest";
import {
  APP_TEXT,
  BOARD_TEXT,
  CONNECTION_TEXT,
  LOBBY_TEXT,
  PLAYERS_TEXT,
  PROMPT_HELPER_TEXT,
  PROMPT_TEXT,
  PROMPT_TYPE_TEXT,
  SITUATION_TEXT,
  STREAM_TEXT,
  THEATER_TEXT,
  TIMELINE_TEXT,
  TURN_STAGE_TEXT,
} from "./uiText";

describe("uiText catalogs", () => {
  it("keeps critical app chrome strings populated", () => {
    expect(APP_TEXT.title.trim().length).toBeGreaterThan(0);
    expect(APP_TEXT.subtitle.trim().length).toBeGreaterThan(0);
    expect(APP_TEXT.waitingTitle(2)).toContain("P2");
    expect(APP_TEXT.turnBanner("P3")).toContain("P3");
  });

  it("keeps lobby/button labels populated", () => {
    expect(LOBBY_TEXT.controlsTitle).toBe("로비 제어");
    expect(LOBBY_TEXT.buttons.quickStartHumanVsAi).toContain("AI 3");
    expect(LOBBY_TEXT.buttons.useSeatToken("2")).toContain("2");
  });

  it("keeps board/connection labels populated", () => {
    expect(BOARD_TEXT.title).toBe("보드");
    expect(BOARD_TEXT.tileKind.S).toBe("운수");
    expect(BOARD_TEXT.owner(4)).toBe("소유자 P4");
    expect(CONNECTION_TEXT.runtimeStatus.running).toBe("실행 중");
    expect(CONNECTION_TEXT.watchdogStatus.stalled_warning).toBe("경고");
  });

  it("keeps theater/stage/prompt phrasing populated", () => {
    expect(THEATER_TEXT.coreActionTitle).toBe("최근 공개 행동");
    expect(THEATER_TEXT.payoffSceneTitle).toBe("같은 턴 결과 장면");
    expect(THEATER_TEXT.toneBadge.critical).toBe("중요");
    expect(TURN_STAGE_TEXT.actorHeadline("P1")).toContain("P1");
    expect(TURN_STAGE_TEXT.currentBeatTitle).toBe("현재 단계");
    expect(PROMPT_TEXT.choice.cashTitle).toBe("현금 선택");
    expect(PROMPT_TEXT.choice.buyTileTitle).toBe("토지 구매");
    expect(PROMPT_TEXT.character.ability("교리 연구관")).toContain("교리 연구관");
  });

  it("keeps players/timeline catalogs populated", () => {
    expect(PLAYERS_TEXT.title).toBe("플레이어");
    expect(PLAYERS_TEXT.stats.position(3)).toBe("위치 3");
    expect(TIMELINE_TEXT.title(5)).toBe("최근 이벤트 (5)");
    expect(SITUATION_TEXT.roundTurn("2", "7")).toBe("2라운드 / 7턴");
  });

  it("keeps prompt type/helper catalogs populated", () => {
    expect(PROMPT_TYPE_TEXT.generic).toBe("선택 요청");
    expect(PROMPT_TYPE_TEXT.labels.movement).toBe("이동값 결정");
    expect(PROMPT_HELPER_TEXT.byType.hidden_trick_card).toContain("히든");
  });

  it("keeps selector-facing stream helpers populated", () => {
    expect(STREAM_TEXT.genericEvent).toBe("이벤트");
    expect(STREAM_TEXT.weatherEffectFallback["긴급 피난"]).toContain("2배");
    expect(STREAM_TEXT.moveSummary("1", "6", 5)).toContain("경로 5칸");
    expect(STREAM_TEXT.markerTransferred(1, 2, 3)).toContain("플립 P3");
    expect(STREAM_TEXT.promptWaiting("토지 구매")).toBe("토지 구매 대기");
  });
});
