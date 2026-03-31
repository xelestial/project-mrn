import type { AlertItem, SituationViewModel } from "../../domain/selectors/streamSelectors";

type SituationPanelProps = {
  model: SituationViewModel;
  alerts?: AlertItem[];
};

export function SituationPanel({ model, alerts = [] }: SituationPanelProps) {
  return (
    <section className="panel">
      <h2>\uD604\uC7AC \uC0C1\uD669</h2>
      <p>\uD589\uB3D9\uC790: {model.actor}</p>
      <p>\uB77C\uC6B4\uB4DC: {model.round}</p>
      <p>\uD134: {model.turn}</p>
      <p>\uC774\uBCA4\uD2B8: {model.eventType}</p>
      <p>\uB0A0\uC528: {model.weather}</p>
      <p>\uB0A0\uC528 \uD6A8\uACFC: {model.weatherEffect}</p>
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
