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

function joinVisible(parts: string[]): string {
  const visible = parts.map((part) => part.trim()).filter((part) => part && part !== "-");
  return visible.length > 0 ? visible.join(" / ") : "-";
}

export function SpectatorTurnPanel({ actorPlayerId, model, latestAction }: SpectatorTurnPanelProps) {
  const { app } = useI18n();
  const title = actorPlayerId === null ? app.spectatorHeadline : app.spectatorTitle(actorPlayerId);
  const progress = model.progressTrail.filter((item) => item.trim());
  const latestActionTitle = latestAction?.label ?? "-";
  const latestActionDetail = latestAction?.detail?.trim() ? latestAction.detail : "-";
  const economyText = joinVisible([model.purchaseSummary, model.rentSummary]);
  const effectText = joinVisible([model.trickSummary, model.fortuneSummary]);

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
          <small>{valueOrDash(model.weatherEffect)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-character">
          <span>{app.spectatorFields.character}</span>
          <strong>{valueOrDash(model.character)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-beat">
          <span>{app.spectatorFields.beat}</span>
          <strong>{valueOrDash(model.currentBeatLabel)}</strong>
          <small>{valueOrDash(model.currentBeatDetail)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-action">
          <span>{app.spectatorFields.action}</span>
          <strong>{valueOrDash(latestActionTitle)}</strong>
          <small>{valueOrDash(latestActionDetail)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-prompt">
          <span>{app.spectatorFields.prompt}</span>
          <strong>{valueOrDash(model.promptSummary)}</strong>
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
          <strong>{valueOrDash(economyText)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-effect">
          <span>{app.spectatorFields.effect}</span>
          <strong>{valueOrDash(effectText)}</strong>
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
