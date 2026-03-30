import type { AlertItem, SituationViewModel } from "../../domain/selectors/streamSelectors";

type SituationPanelProps = {
  model: SituationViewModel;
  alerts?: AlertItem[];
};

export function SituationPanel({ model, alerts = [] }: SituationPanelProps) {
  return (
    <section className="panel">
      <h2>Situation</h2>
      <p>Actor: {model.actor}</p>
      <p>Round: {model.round}</p>
      <p>Turn: {model.turn}</p>
      <p>Event: {model.eventType}</p>
      <p>Weather: {model.weather}</p>
      {alerts.length > 0 ? (
        <div className="alert-stack" aria-live="polite">
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

