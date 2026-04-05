import type { AlertItem, SituationViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type SituationPanelProps = {
  model: SituationViewModel;
  alerts?: AlertItem[];
};

function valueOrDash(value: string, emptyText: string): string {
  const trimmed = value.trim();
  return trimmed ? trimmed : emptyText;
}

function infoCard(label: string, value: string, emptyText: string, detail?: string) {
  return (
    <article className="situation-card">
      <span>{label}</span>
      <strong>{valueOrDash(value, emptyText)}</strong>
      {detail ? <small>{valueOrDash(detail, emptyText)}</small> : null}
    </article>
  );
}

export function SituationPanel({ model, alerts = [] }: SituationPanelProps) {
  const { situation } = useI18n();
  return (
    <section className="panel situation-panel">
      <div className="situation-panel-head">
        <h2>{situation.title}</h2>
      </div>

      <div className="situation-grid">
        {infoCard(situation.cards.actor, model.actor, situation.empty)}
        {infoCard(situation.cards.roundTurn, situation.roundTurn(model.round, model.turn), situation.empty)}
        {infoCard(situation.cards.event, model.eventType, situation.empty)}
        {infoCard(situation.cards.weather, model.weather, situation.empty)}
        <article className="situation-card situation-card-wide">
          <span>{situation.cards.weatherEffect}</span>
          <strong>{valueOrDash(model.weatherEffect, situation.empty)}</strong>
        </article>
      </div>

      {alerts.length > 0 ? (
        <div className="alert-stack" aria-live="polite">
          <strong className="situation-alert-title">{situation.alertsTitle}</strong>
          {alerts.map((alert) => (
            <article
              key={`alert-${alert.seq}`}
              className={alert.severity === "critical" ? "alert-item alert-critical" : "alert-item alert-warning"}
            >
              <strong>
                {alert.title} #{alert.seq}
              </strong>
              <small>{alert.detail}</small>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
