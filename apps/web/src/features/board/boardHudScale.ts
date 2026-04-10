export type BoardHudScale = {
  sceneScale: number;
  density: "compact" | "regular" | "comfortable";
  overlayGap: number;
  overlayGapTight: number;
  panelPadding: number;
  cardPadding: number;
  panelRadius: number;
  cardRadius: number;
  titleFontSize: number;
  emphasisFontSize: number;
  bodyFontSize: number;
  smallFontSize: number;
  chipFontSize: number;
  statFontSize: number;
  promptMaxHeight: number;
  choiceMinWidth: number;
  handCardMinWidth: number;
  handGridColumns: number;
};

export type BoardHudScaleInput = {
  boardWidth: number;
  boardHeight: number;
  viewportWidth: number;
  viewportHeight: number;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function roundToTenths(value: number): number {
  return Math.round(value * 10) / 10;
}

function roundPixel(value: number): number {
  return Math.round(value);
}

export function computeBoardHudScale({
  boardWidth,
  boardHeight,
  viewportWidth,
  viewportHeight,
}: BoardHudScaleInput): BoardHudScale {
  const safeBoardWidth = Math.max(0, boardWidth);
  const safeBoardHeight = Math.max(0, boardHeight);
  const safeViewportWidth = Math.max(0, viewportWidth || boardWidth);
  const safeViewportHeight = Math.max(0, viewportHeight || boardHeight);
  const widthScale = safeViewportWidth > 0 ? safeViewportWidth / 1180 : 1;
  const heightScale = safeViewportHeight > 0 ? safeViewportHeight / 520 : 1;
  const boardScale = safeBoardHeight > 0 ? safeBoardHeight / 720 : 1;
  const sceneScale = clamp(Math.min(widthScale, heightScale, boardScale), 0.72, 1.14);
  const density = sceneScale < 0.88 ? "compact" : sceneScale > 1.04 ? "comfortable" : "regular";

  return {
    sceneScale: roundToTenths(sceneScale),
    density,
    overlayGap: roundPixel(clamp(14 * sceneScale, 10, 18)),
    overlayGapTight: roundPixel(clamp(8 * sceneScale, 6, 12)),
    panelPadding: roundPixel(clamp(14 * sceneScale, 10, 18)),
    cardPadding: roundPixel(clamp(12 * sceneScale, 10, 16)),
    panelRadius: roundPixel(clamp(18 * sceneScale, 14, 22)),
    cardRadius: roundPixel(clamp(14 * sceneScale, 12, 18)),
    titleFontSize: roundPixel(clamp(24 * sceneScale, 18, 30)),
    emphasisFontSize: roundPixel(clamp(18 * sceneScale, 14, 22)),
    bodyFontSize: roundPixel(clamp(13 * sceneScale, 11, 16)),
    smallFontSize: roundPixel(clamp(10.5 * sceneScale, 9, 12)),
    chipFontSize: roundPixel(clamp(11 * sceneScale, 10, 13)),
    statFontSize: roundPixel(clamp(10 * sceneScale, 9, 12)),
    promptMaxHeight: roundPixel(clamp(safeViewportHeight * 0.5, 260, 560)),
    choiceMinWidth: roundPixel(clamp(safeViewportWidth / 4.2, 180, 280)),
    handCardMinWidth: roundPixel(clamp(safeViewportWidth / 5.4, 170, 260)),
    handGridColumns: 5,
  };
}
