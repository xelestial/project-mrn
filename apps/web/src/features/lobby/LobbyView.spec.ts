import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { LobbyView, type LobbySeatType } from "./LobbyView";

const noop = vi.fn();

function renderLobby(overrides: Partial<React.ComponentProps<typeof LobbyView>> = {}) {
  const seatTypes: LobbySeatType[] = ["human", "ai", "ai", "ai"];

  return renderToStaticMarkup(
    React.createElement(LobbyView, {
      busy: false,
      locale: "ko",
      serverBaseInput: "http://127.0.0.1:9090",
      serverConnected: false,
      roomTitleInput: "MRN Room",
      nicknameInput: "Player",
      hostSeatInput: "1",
      seatTypes,
      activeRoom: null,
      activeRoomSeat: null,
      rooms: [],
      notice: "",
      error: "",
      onServerBaseInput: noop,
      onConnectServer: noop,
      onRoomTitleInput: noop,
      onNicknameInput: noop,
      onHostSeatInput: noop,
      onSeatTypeChange: noop,
      onCreateRoom: noop,
      onQuickStartHumanVsAi: noop,
      onRefreshRooms: noop,
      onJoinRoom: noop,
      onToggleReady: noop,
      onStartRoom: noop,
      onLeaveRoom: noop,
      ...overrides,
    }),
  );
}

describe("LobbyView", () => {
  it("presents quick start as the primary action and keeps server settings collapsed", () => {
    const html = renderLobby();

    expect(html).toContain('data-testid="lobby-primary-quick-start"');
    expect(html).toContain("lobby-primary-action");
    expect(html).toContain("<summary");
    expect(html).toContain("서버 설정");
    expect(html).not.toContain('<details class="lobby-server-drawer" open');
  });

  it("gives the empty rooms state a next action instead of a dead end", () => {
    const html = renderLobby({ serverConnected: true });

    expect(html).toContain("바로 AI 대전을 시작하거나 새 방을 만들 수 있습니다.");
    expect(html).toContain('data-testid="lobby-empty-quick-start"');
  });
});
