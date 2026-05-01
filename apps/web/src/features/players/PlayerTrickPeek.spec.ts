import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PlayerTrickPeek } from "./PlayerTrickPeek";

describe("PlayerTrickPeek", () => {
  it("renders public trick names and hidden tricks as card backs", () => {
    const html = renderToStaticMarkup(
      React.createElement(PlayerTrickPeek, {
        locale: "ko",
        playerLabel: "P2",
        publicTricks: ["이럇!", "강제 매각"],
        hiddenTrickCount: 2,
      }),
    );

    expect(html).toContain("이럇!");
    expect(html).toContain("강제 매각");
    expect(html).toContain("공개 2 / 비공개 2");
    expect(html.match(/data-card-visibility="hidden"/g)?.length).toBe(2);
    expect(html.match(/match-table-player-trick-card-back/g)?.length).toBe(2);
  });
});
