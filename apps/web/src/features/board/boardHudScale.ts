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
  controlHeight: number;
  weatherMinHeight: number;
  playerCardMinHeight: number;
  activeCharacterMinHeight: number;
  promptMaxHeight: number;
  promptShellMaxWidth: number;
  handTrayMaxHeight: number;
  promptMiddleReserveBottom: number;
  choiceMinWidth: number;
  choiceMinHeight: number;
  handCardMinWidth: number;
  handCardMinHeight: number;
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
  const sceneScale = clamp(Math.min(widthScale, heightScale, boardScale), 0.62, 1.12);
  const density = sceneScale < 0.88 ? "compact" : sceneScale > 1.04 ? "comfortable" : "regular";
  const safeBandHeight = clamp(safeViewportHeight, 300, 760);

  return {
    sceneScale: roundToTenths(sceneScale),
    density,
    overlayGap: roundPixel(clamp(14 * sceneScale, 8, 18)),
    overlayGapTight: roundPixel(clamp(8 * sceneScale, 5, 12)),
    panelPadding: roundPixel(clamp(14 * sceneScale, 8, 18)),
    cardPadding: roundPixel(clamp(12 * sceneScale, 8, 16)),
    panelRadius: roundPixel(clamp(18 * sceneScale, 14, 22)),
    cardRadius: roundPixel(clamp(14 * sceneScale, 12, 18)),
    titleFontSize: roundPixel(clamp(24 * sceneScale, 18, 30)),
    emphasisFontSize: roundPixel(clamp(18 * sceneScale, 14, 22)),
    bodyFontSize: roundPixel(clamp(13 * sceneScale, 10, 16)),
    smallFontSize: roundPixel(clamp(10.5 * sceneScale, 8, 12)),
    chipFontSize: roundPixel(clamp(11 * sceneScale, 8, 13)),
    statFontSize: roundPixel(clamp(10 * sceneScale, 8, 12)),
    controlHeight: roundPixel(clamp(42 * sceneScale, 34, 46)),
    weatherMinHeight: roundPixel(clamp(134 * sceneScale, 98, 150)),
    playerCardMinHeight: roundPixel(clamp(136 * sceneScale, 102, 154)),
    activeCharacterMinHeight: roundPixel(clamp(68 * sceneScale, 52, 84)),
    promptMaxHeight: roundPixel(clamp(safeBandHeight * 0.33, 196, 360)),
    promptShellMaxWidth: roundPixel(clamp(safeViewportWidth * 0.92, 960, 1560)),
    handTrayMaxHeight: roundPixel(clamp(safeBandHeight * 0.2, 136, 220)),
    promptMiddleReserveBottom: roundPixel(clamp(safeBandHeight * 0.24, 150, 250)),
    choiceMinWidth: roundPixel(clamp(safeViewportWidth / 5.1, 150, 250)),
    choiceMinHeight: roundPixel(clamp(142 * sceneScale, 104, 156)),
    handCardMinWidth: roundPixel(clamp(safeViewportWidth / 5.8, 138, 220)),
    handCardMinHeight: roundPixel(clamp(118 * sceneScale, 88, 136)),
    handGridColumns: 5,
  };
}
