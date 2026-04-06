import { describe, expect, it } from "vitest";
import {
  APP_TEXT,
  BOARD_TEXT,
  PROMPT_TEXT,
} from "./uiText";
import { DEFAULT_APP_TEXT, DEFAULT_BOARD_TEXT, DEFAULT_PROMPT_TEXT } from "../../i18n/defaultText";

describe("uiText compatibility shim", () => {
  it("re-exports default app text", () => {
    expect(APP_TEXT).toBe(DEFAULT_APP_TEXT);
  });

  it("re-exports default board text", () => {
    expect(BOARD_TEXT).toBe(DEFAULT_BOARD_TEXT);
  });

  it("re-exports default prompt text", () => {
    expect(PROMPT_TEXT).toBe(DEFAULT_PROMPT_TEXT);
  });
});
