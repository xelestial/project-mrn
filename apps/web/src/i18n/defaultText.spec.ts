import { describe, expect, it } from "vitest";
import {
  DEFAULT_APP_TEXT,
  DEFAULT_BOARD_TEXT,
  DEFAULT_CONNECTION_TEXT,
  DEFAULT_LOBBY_TEXT,
  DEFAULT_PLAYERS_TEXT,
  DEFAULT_PROMPT_HELPER_TEXT,
  DEFAULT_PROMPT_TEXT,
  DEFAULT_PROMPT_TYPE_TEXT,
  DEFAULT_SITUATION_TEXT,
  DEFAULT_STREAM_TEXT,
  DEFAULT_THEATER_TEXT,
  DEFAULT_TIMELINE_TEXT,
  DEFAULT_TURN_STAGE_TEXT,
} from "./defaultText";

describe("defaultText catalogs", () => {
  it("keeps critical app chrome strings populated", () => {
    expect(DEFAULT_APP_TEXT.title.trim().length).toBeGreaterThan(0);
    expect(DEFAULT_APP_TEXT.subtitle.trim().length).toBeGreaterThan(0);
    expect(DEFAULT_APP_TEXT.waitingTitle(2)).toContain("P2");
    expect(DEFAULT_APP_TEXT.turnBanner("P3")).toContain("P3");
  });

  it("keeps lobby/button labels populated", () => {
    expect(DEFAULT_LOBBY_TEXT.controlsTitle).toBe("로비 제어");
    expect(DEFAULT_LOBBY_TEXT.buttons.quickStartHumanVsAi).toContain("AI 3");
    expect(DEFAULT_LOBBY_TEXT.buttons.useSeatToken("2")).toContain("2");
  });

  it("keeps board/connection labels populated", () => {
    expect(DEFAULT_BOARD_TEXT.title).toBe("보드");
    expect(DEFAULT_BOARD_TEXT.tileKind.S).toBe("운수");
    expect(DEFAULT_BOARD_TEXT.owner(4)).toBe("소유자 P4");
    expect(DEFAULT_CONNECTION_TEXT.runtimeStatus.running).toBe("실행 중");
    expect(DEFAULT_CONNECTION_TEXT.watchdogStatus.stalled_warning).toBe("경고");
  });

  it("keeps theater/stage/prompt phrasing populated", () => {
    expect(DEFAULT_THEATER_TEXT.coreActionTitle).toBe("최근 공개 행동");
    expect(DEFAULT_THEATER_TEXT.payoffSceneTitle).toBe("같은 턴 결과 장면");
    expect(DEFAULT_THEATER_TEXT.toneBadge.critical).toBe("중요");
    expect(DEFAULT_TURN_STAGE_TEXT.actorHeadline("P1")).toContain("P1");
    expect(DEFAULT_TURN_STAGE_TEXT.currentBeatTitle).toBe("현재 단계");
    expect(DEFAULT_PROMPT_TEXT.choice.cashTitle).toBe("현금 선택");
    expect(DEFAULT_PROMPT_TEXT.choice.buyTileTitle).toBe("토지 구매");
    expect(DEFAULT_PROMPT_TEXT.character.ability("교리 연구관")).toContain("교리 연구관");
  });

  it("keeps players/timeline catalogs populated", () => {
    expect(DEFAULT_PLAYERS_TEXT.title).toBe("플레이어");
    expect(DEFAULT_PLAYERS_TEXT.stats.position(3)).toBe("위치 3");
    expect(DEFAULT_TIMELINE_TEXT.title(5)).toBe("최근 이벤트 (5)");
    expect(DEFAULT_SITUATION_TEXT.roundTurn("2", "7")).toBe("2라운드 / 7턴");
  });

  it("keeps prompt type/helper catalogs populated", () => {
    expect(DEFAULT_PROMPT_TYPE_TEXT.generic).toBe("선택 요청");
    expect(DEFAULT_PROMPT_TYPE_TEXT.labels.movement).toBe("이동값 결정");
    expect(DEFAULT_PROMPT_HELPER_TEXT.byType.hidden_trick_card).toContain("히든");
  });

  it("keeps selector-facing stream helpers populated", () => {
    expect(DEFAULT_STREAM_TEXT.genericEvent).toBe("이벤트");
    expect(DEFAULT_STREAM_TEXT.weatherEffectFallback["긴급 피난"]).toContain("2배");
    expect(DEFAULT_STREAM_TEXT.moveSummary("1", "6", 5)).toContain("경로 5칸");
    expect(DEFAULT_STREAM_TEXT.markerTransferred(1, 2, 3)).toContain("플립 P3");
    expect(DEFAULT_STREAM_TEXT.promptWaiting("토지 구매")).toBe("토지 구매 대기");
  });
});
