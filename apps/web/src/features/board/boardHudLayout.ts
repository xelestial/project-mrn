export type RectLike = {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
};

export type BoardHudFrame = {
  boardWidth: number;
  boardHeight: number;
  safeTop: number;
  safeBottomGap: number;
  safeLeft: number;
  safeRightGap: number;
  viewportLeft: number;
  viewportTop: number;
  viewportWidth: number;
  viewportHeight: number;
  promptTopInset: number;
  handTrayTopInset: number;
  handTrayBottomGap: number;
  handTrayHeight: number;
};

export type BoardHudLayoutInput = {
  scrollRect: RectLike;
  topTileRect?: RectLike | null;
  bottomTileRect?: RectLike | null;
  leftTileRect?: RectLike | null;
  rightTileRect?: RectLike | null;
  promptTopTileRect?: RectLike | null;
  handTrayTopTileRect?: RectLike | null;
  handTrayBottomTileRect?: RectLike | null;
};

function clampToPixels(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.round(value));
}

export function computeBoardHudFrame({
  scrollRect,
  topTileRect = null,
  bottomTileRect = null,
  leftTileRect = null,
  rightTileRect = null,
  promptTopTileRect = null,
  handTrayTopTileRect = null,
  handTrayBottomTileRect = null,
}: BoardHudLayoutInput): BoardHudFrame | null {
  if (!scrollRect || !leftTileRect || !rightTileRect) {
    return null;
  }

  const boardWidth = clampToPixels(scrollRect.width);
  const boardHeight = clampToPixels(scrollRect.height);
  const safeTop = topTileRect ? clampToPixels(topTileRect.top - scrollRect.top) : 0;
  const safeBottomGap = bottomTileRect ? clampToPixels(scrollRect.bottom - bottomTileRect.bottom) : 0;
  const safeLeft = clampToPixels(leftTileRect.left - scrollRect.left);
  const safeRightGap = clampToPixels(scrollRect.right - rightTileRect.right);
  const promptTop = promptTopTileRect ? clampToPixels(promptTopTileRect.top - scrollRect.top) : safeTop;
  const handTrayTop = handTrayTopTileRect ? clampToPixels(handTrayTopTileRect.top - scrollRect.top) : boardHeight - safeBottomGap;
  const handTrayBottom = handTrayBottomTileRect
    ? clampToPixels(handTrayBottomTileRect.bottom - scrollRect.top)
    : boardHeight - safeBottomGap;

  return {
    boardWidth,
    boardHeight,
    safeTop,
    safeBottomGap,
    safeLeft,
    safeRightGap,
    viewportLeft: clampToPixels(scrollRect.left + safeLeft),
    viewportTop: clampToPixels(scrollRect.top + safeTop),
    viewportWidth: clampToPixels(boardWidth - safeLeft - safeRightGap),
    viewportHeight: clampToPixels(boardHeight - safeTop - safeBottomGap),
    promptTopInset: clampToPixels(promptTop - safeTop),
    handTrayTopInset: clampToPixels(handTrayTop - safeTop),
    handTrayBottomGap: handTrayBottomTileRect ? clampToPixels(scrollRect.bottom - handTrayBottomTileRect.bottom) : safeBottomGap,
    handTrayHeight: clampToPixels(handTrayBottom - handTrayTop),
  };
}

export function sameBoardHudFrame(left: BoardHudFrame | null, right: BoardHudFrame | null): boolean {
  if (left === right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return (
    left.boardWidth === right.boardWidth &&
    left.boardHeight === right.boardHeight &&
    left.safeTop === right.safeTop &&
    left.safeBottomGap === right.safeBottomGap &&
    left.safeLeft === right.safeLeft &&
    left.safeRightGap === right.safeRightGap &&
    left.viewportLeft === right.viewportLeft &&
    left.viewportTop === right.viewportTop &&
    left.viewportWidth === right.viewportWidth &&
    left.viewportHeight === right.viewportHeight &&
    left.promptTopInset === right.promptTopInset &&
    left.handTrayTopInset === right.handTrayTopInset &&
    left.handTrayBottomGap === right.handTrayBottomGap &&
    left.handTrayHeight === right.handTrayHeight
  );
}
