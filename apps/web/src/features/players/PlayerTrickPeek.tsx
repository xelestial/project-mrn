type PlayerTrickPeekProps = {
  locale: string;
  playerLabel: string;
  publicTricks: readonly string[];
  hiddenTrickCount: number;
  testId?: string;
};

function normalizeCount(count: number): number {
  if (!Number.isFinite(count)) {
    return 0;
  }
  return Math.max(0, Math.trunc(count));
}

export function PlayerTrickPeek({
  locale,
  playerLabel,
  publicTricks,
  hiddenTrickCount,
  testId,
}: PlayerTrickPeekProps) {
  const safeHiddenTrickCount = normalizeCount(hiddenTrickCount);
  const hiddenTrickLabel = locale === "ko" ? "비공개 잔꾀" : "Hidden trick";

  return (
    <section
      className="match-table-player-trick-peek"
      data-testid={testId}
      aria-label={locale === "ko" ? `${playerLabel} 보유 잔꾀` : `${playerLabel} trick cards`}
    >
      <div className="match-table-player-trick-peek-head">
        <strong>{locale === "ko" ? "보유 잔꾀" : "Trick cards"}</strong>
        <span>
          {locale === "ko"
            ? `공개 ${publicTricks.length} / 비공개 ${safeHiddenTrickCount}`
            : `Public ${publicTricks.length} / Hidden ${safeHiddenTrickCount}`}
        </span>
      </div>
      <div className="match-table-player-trick-peek-grid">
        {publicTricks.map((trickName, index) => (
          <article
            key={`public-${trickName}-${index}`}
            className="match-table-player-trick-mini-card match-table-player-trick-mini-card-public"
            data-card-visibility="public"
          >
            <small>{locale === "ko" ? "공개패" : "Public"}</small>
            <strong>{trickName}</strong>
          </article>
        ))}
        {Array.from({ length: safeHiddenTrickCount }).map((_, index) => (
          <article
            key={`hidden-${index}`}
            className="match-table-player-trick-mini-card match-table-player-trick-mini-card-hidden"
            data-card-visibility="hidden"
            aria-label={hiddenTrickLabel}
          >
            <div className="match-table-player-trick-card-back" aria-hidden="true" />
            <strong>{hiddenTrickLabel}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}
