import type { AlertItem, SituationViewModel } from "../../domain/selectors/streamSelectors";

type SituationPanelProps = {
  model: SituationViewModel;
  alerts?: AlertItem[];
};

export function SituationPanel({ model, alerts = [] }: SituationPanelProps) {
  return (
    <section className="panel">
      <h2>현재 상황</h2>
      <p>행동자: {model.actor}</p>
      <p>라운드: {model.round}</p>
      <p>턴: {model.turn}</p>
      <p>이벤트: {model.eventType}</p>
      <p>날씨: {model.weather}</p>
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
