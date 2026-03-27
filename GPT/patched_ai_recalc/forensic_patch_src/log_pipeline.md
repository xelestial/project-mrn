# log_pipeline.py

## 역할
배치 로그 분석 파이프라인.

- `simulate_with_logs.py`가 만든 `games.jsonl`을 읽는다.
- 각 `turn` runtime event를 기반으로 턴 단위 특징량을 뽑는다.
- 최종 승자 라벨을 붙여 턴별 승률 추정 학습셋을 만든다.
- 간단한 로지스틱 회귀 모델을 학습해 `predicted_win_prob`를 각 턴 row에 붙인다.
- 게임/플레이어별 결정적 턴(`pivotal_turns`)을 저장한다.

## 설계 의도
- 매번 raw log를 수동으로 뒤지지 않기 위한 자동 분석 파이프라인.
- 로그가 쌓일수록 `turn_features.jsonl/csv`와 `win_model.json`이 함께 갱신되도록 하는 기반.
- 현재 버전은 **최종 승리 여부를 예측하는 baseline**이다.
- 의도: 이후에는 backward regression, horizon별 모델, 이벤트 가치 학습으로 확장한다.

## 산출물
- `summary.json`: 기본 분석 요약
- `turn_features.jsonl` / `turn_features.csv`: 턴 단위 특징량 + 최종 승리 라벨 + 예측 승률
- `win_model.json`: baseline 로지스틱 가중치
- `feature_importance.json`: 절대 가중치 기준 특징 중요도
- `pivotal_turns.json`: 플레이어별 승률 점프가 가장 컸던 턴

## 사용 예시
```bash
python log_pipeline.py pipeline --simulations 100 --seed 42 --output-dir analysis_pipeline
python log_pipeline.py analyze --games-jsonl analysis_pipeline/simulation/games.jsonl --output-dir analysis_pipeline/analysis
```

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.
