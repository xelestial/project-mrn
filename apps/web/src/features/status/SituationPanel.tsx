import type { SituationViewModel } from "../../domain/selectors/streamSelectors";

type SituationPanelProps = {
  model: SituationViewModel;
};

export function SituationPanel({ model }: SituationPanelProps) {
  return (
    <section className="panel">
      <h2>현재 상황</h2>
      <p>행동자: {model.actor}</p>
      <p>라운드: {model.round}</p>
      <p>턴: {model.turn}</p>
      <p>이벤트: {model.eventType}</p>
      <p>날씨: {model.weather}</p>
    </section>
  );
}
