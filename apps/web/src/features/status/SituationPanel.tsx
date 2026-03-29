import type { SituationViewModel } from "../../domain/selectors/streamSelectors";

type SituationPanelProps = {
  model: SituationViewModel;
};

export function SituationPanel({ model }: SituationPanelProps) {
  return (
    <section className="panel">
      <h2>Situation</h2>
      <p>Actor: {model.actor}</p>
      <p>Round: {model.round}</p>
      <p>Turn: {model.turn}</p>
      <p>Type: {model.eventType}</p>
      <p>Weather: {model.weather}</p>
    </section>
  );
}

