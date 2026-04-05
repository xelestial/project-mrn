import type { CoreActionItem, TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type SpectatorTurnPanelProps = {
  actorPlayerId: number | null;
  model: TurnStageViewModel;
  latestAction: CoreActionItem | null;
};

function valueOrDash(value: string): string {
  const trimmed = value.trim();
  return trimmed ? trimmed : "-";
}

export function SpectatorTurnPanel({ actorPlayerId, model, latestAction }: SpectatorTurnPanelProps) {
  const { app } = useI18n();
  const title = actorPlayerId === null ? app.spectatorHeadline : app.spectatorTitle(actorPlayerId);
  const progress = model.progressTrail.filter((item) => item.trim());
  const latestActionText =
    latestAction && latestAction.detail.trim() ? `${latestAction.label} / ${latestAction.detail}` : latestAction?.label ?? "-";

  return (
    <section className="panel spectator-turn-panel" data-testid="spectator-turn-panel">
      <div className="spectator-turn-head">
        <div>
          <h2>{app.spectatorHeadline}</h2>
          <strong>{title}</strong>
        </div>
        <p>
          <span className="spinner" aria-hidden="true" /> {app.spectatorDescription}
        </p>
      </div>

      <div className="spectator-turn-grid">
        <article className="spectator-turn-card" data-testid="spectator-turn-weather">
          <span>{app.spectatorFields.weather}</span>
          <strong>{valueOrDash(model.weatherName)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-beat">
          <span>{app.spectatorFields.beat}</span>
          <strong>{`${valueOrDash(model.currentBeatLabel)} / ${valueOrDash(model.currentBeatDetail)}`}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-action">
          <span>{app.spectatorFields.action}</span>
          <strong>{valueOrDash(latestActionText)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-move">
          <span>{app.spectatorFields.move}</span>
          <strong>{valueOrDash(model.moveSummary)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-landing">
          <span>{app.spectatorFields.landing}</span>
          <strong>{valueOrDash(model.landingSummary)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-economy">
          <span>{app.spectatorFields.economy}</span>
          <strong>{valueOrDash([model.purchaseSummary, model.rentSummary].filter((item) => item.trim()).join(" / "))}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-effect">
          <span>{app.spectatorFields.effect}</span>
          <strong>{valueOrDash([model.trickSummary, model.fortuneSummary].filter((item) => item.trim()).join(" / "))}</strong>
        </article>
      </div>

      <div className="spectator-turn-progress" data-testid="spectator-turn-progress">
        <span>{app.spectatorFields.progress}</span>
        {progress.length > 0 ? (
          <div className="spectator-turn-progress-list">
            {progress.map((step) => (
              <small key={step}>{step}</small>
            ))}
          </div>
        ) : (
          <strong>-</strong>
        )}
      </div>
    </section>
  );
}
