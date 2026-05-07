# AI Reinforcement Learning Plan

Status: DRAFT - superseded by deep RL implementation plan for the next work track
Owner: Engine / AI policy
Created: 2026-05-07

Deep RL pivot: 2026-05-07
Implementation plan: `docs/superpowers/plans/2026-05-07-deep-rl-game-ai.md`

## Goal

게임 AI를 휴리스틱 튜닝만으로 밀지 않고, 시뮬레이션 로그에서 반복적으로 관측되는 고수익/대손실 패턴을 학습 신호로 바꾼다.

첫 학습 표적은 두 가지다.

1. 게임에서 가장 크게 돈을 벌 수 있었던 기회
2. 게임 내에서 가장 크게 돈을 잃었던 사건

원래 계획은 여기서 바로 딥 강화학습으로 가지 않는 것이었다. 그러나 사용자 방향이 딥 RL로 바뀌었으므로 이 문서는 하위 진단/보상 설계 문서로 유지한다. 돈 이벤트 ledger는 폐기하지 않는다. 딥 RL의 reward component, replay analysis, 실패 attribution으로 재사용한다.

웹소켓 불안정은 이 문서의 학습 목표가 아니다. 웹소켓/런타임 복원 문제는 서버 신뢰성 트랙에서 계속 막아야 한다. RL은 그 위에서 AI 의사결정 품질을 개선하는 별도 트랙이다.

## Current Baseline

이미 있는 자산:

- `engine/ai_policy.py`: 현재 운영 휴리스틱 정책
- `engine/policy/decision/*`: 구매, 이동, LAP 보상, 잔꾀, 인물 선택 등 결정 단위 분리
- `engine/policy/pipeline_trace.py`: 결정별 feature / detector / final choice payload 구조
- `engine/policy_hooks.py`: 정책 결정 전후 hook
- `engine/log_pipeline.py`: `games.jsonl`에서 턴 feature를 추출하고 단순 승률 모델을 만드는 분석 파이프라인
- `engine/analyze_ai_decisions.py`: AI decision trace 집계 도구

부족한 것:

- 개별 현금 변화 사건을 정규화한 event ledger
- "실제로 번 돈"과 "벌 수 있었는데 놓친 돈"의 분리
- 손실 사건 직전의 선택과 결과를 잇는 attribution
- 학습 결과를 정책 점수에 안전하게 주입하는 adapter
- 기존 휴리스틱 대비 regression gate

## Learning Target 1: Biggest Money Opportunity

정의:

한 플레이어가 특정 시점에서 선택 가능했던 합법 행동 중, 단기 또는 중기 현금 기대값이 가장 큰 선택지를 말한다.

처음에는 아래를 돈벌이 기회로 본다.

- 무료/저가 구매로 고렌트 타일 확보
- 독점 완성 또는 독점 차단 구매
- 사기꾼 인수로 고가 타일/승점 코인 탈취
- 객주/파발꾼/이동 카드로 LAP 보상 연쇄 진입
- 아전/산적/탐관오리/성물 수집가 계열 현금 흡수 타이밍
- 렌트 면제/회피로 사실상 현금 손실을 막은 선택
- 초기 보상/LAP 보상에서 현금이 생존과 다음 구매를 동시에 여는 경우

필요한 라벨:

- `cash_gain_actual`: 사건 직후 내 현금 증가량
- `cash_gain_effective`: 실제 증가량 + 회피한 손실 + 확보한 무료 구매 가치
- `opportunity_value`: 선택 가능한 후보 중 최대 기대 현금 가치
- `missed_opportunity_value`: 선택하지 않은 최고 후보 가치 - 실제 선택 가치
- `horizon_turns`: 1턴, 2턴, 라운드 종료, 게임 종료 중 어느 기간으로 평가했는지

초기 모델은 "이 선택이 돈을 벌 기회였나"를 회귀/랭킹으로 학습한다. 정책에 바로 액션을 맡기지 않고, 기존 휴리스틱 점수에 `learned_cash_opportunity_bonus`를 더하는 방식으로만 사용한다.

## Learning Target 2: Biggest Money Loss

정의:

한 플레이어가 특정 사건 또는 직전 선택 때문에 큰 현금 손실, 파산, 구매 기회 상실을 겪은 경우다.

처음에는 아래를 손실 사건으로 본다.

- 적 소유 타일 렌트 지불
- 짐/정리 비용으로 현금 증발 또는 파산
- 무리한 구매 직후 reserve 붕괴
- 고가 사기꾼 인수 실패 또는 생존 불가능한 인수
- 불리한 날씨/운수/잔꾀 효과를 막지 못한 손실
- 이동 카드 사용으로 적 렌트 구간에 진입
- 현금 대신 조각/승점 보상을 고른 뒤 즉시 렌트/정리 압박에 빠진 경우

필요한 라벨:

- `cash_loss_actual`: 사건 직후 내 현금 감소량
- `cash_loss_effective`: 실제 감소량 + 파산 shortfall + 잃은 구매/생존 기회
- `avoidable_loss`: 직전 합법 선택 중 더 나은 선택으로 줄일 수 있었던 손실
- `loss_cause`: `rent`, `cleanup`, `bad_purchase`, `bad_movement`, `bad_reward`, `hostile_effect`, `bankruptcy`
- `attribution_decision_id`: 손실 직전에 영향을 준 결정 ID

초기 모델은 "이 선택이 대손실로 이어질 위험이 있나"를 분류/회귀로 학습한다. 정책 주입은 `learned_cash_loss_penalty`로 제한한다.

## Data Model

새 학습 행은 턴 단위가 아니라 사건 단위여야 한다.

```json
{
  "game_id": 123,
  "seed": 42,
  "round_index": 3,
  "turn_index_global": 17,
  "player_id": 2,
  "event_id": "g123:t17:p2:rent",
  "event_type": "cash_loss",
  "cause": "rent",
  "cash_before": 13,
  "cash_after": 5,
  "cash_delta": -8,
  "effective_cash_delta": -8,
  "bankrupt": false,
  "state_features": {
    "position": 11,
    "cash": 13,
    "shards": 3,
    "tiles_owned": 4,
    "score": 6,
    "cash_after_reserve": 2.0,
    "money_distress": 0.4,
    "two_turn_lethal_prob": 0.08
  },
  "decision_context": {
    "decision_name": "choose_movement",
    "chosen_action": "use_cards:false",
    "legal_actions": ["use_cards:false", "use_cards:true:1+3"],
    "trace": {}
  },
  "outcome": {
    "won": false,
    "turns_to_end": 12,
    "final_rank": 3
  }
}
```

## Implementation Phases

### Phase 1: Cash Event Ledger

Files:

- Modify: `engine/log_pipeline.py`
- Modify: `engine/test_log_pipeline.py`
- Read: `engine/effect_handlers.py`
- Read: `engine/policy_hooks.py`

Work:

1. Add `extract_cash_event_rows(games)` next to `extract_turn_feature_rows`.
2. Parse action log events with `cash_before`, `cash_after`, `cash_delta`, `cash_delta`, `cash_shortfall`, `rent_context`, `purchase_context`, `bankrupt`.
3. Normalize event causes into a stable enum:
   - `rent`
   - `purchase`
   - `takeover`
   - `lap_reward`
   - `start_reward`
   - `cash_gain_effect`
   - `cash_loss_effect`
   - `cleanup`
   - `bankruptcy`
4. Emit `cash_events.jsonl` and `cash_events.csv`.
5. Test with synthetic `games.jsonl` rows that include rent loss, reward gain, purchase cost, and bankruptcy.

Exit criteria:

- Every non-zero cash movement in action logs has one cash event row.
- Bankruptcy rows preserve `cash_shortfall`.
- Existing `turn_features` output remains unchanged.

### Phase 2: Opportunity / Loss Ranking

Files:

- Modify: `engine/log_pipeline.py`
- Create: `engine/test_cash_event_attribution.py`

Work:

1. Add `cash_event_score(row)`:
   - positive values rank money opportunities
   - negative values rank losses
   - bankruptcy gets an additional large negative effective value
2. Add `compute_top_cash_opportunities(rows, limit=200)`.
3. Add `compute_top_cash_losses(rows, limit=200)`.
4. Write:
   - `top_cash_opportunities.json`
   - `top_cash_losses.json`
5. Include nearby decision trace IDs when available.

Exit criteria:

- Running the pipeline prints the top money-making and top money-losing event categories.
- The top loss list is not just bankruptcies; large rent/cleanup mistakes also appear.

### Phase 3: Decision Attribution

Files:

- Modify: `engine/policy_hooks.py`
- Modify: `engine/log_pipeline.py`
- Modify: `engine/test_log_pipeline.py`

Work:

1. Extend `PolicyDecisionLogHook` to include a stable `decision_event_id`.
2. Store compact before/after feature snapshots for decisions that can affect money:
   - `choose_purchase_tile`
   - `choose_movement`
   - `choose_trick_to_use`
   - `choose_lap_reward`
   - `choose_start_reward`
   - `choose_draft_card`
   - `choose_final_character`
3. In `extract_cash_event_rows`, attach the nearest prior decision from the same player within the same turn.
4. Add attribution windows:
   - immediate: same event group
   - short: same turn
   - medium: next 2 own turns

Exit criteria:

- A rent loss caused by movement can point back to `choose_movement`.
- A reserve failure after purchase can point back to `choose_purchase_tile`.
- A bad reward selection can point back to `choose_lap_reward` or `choose_start_reward`.

### Phase 4: Offline Cash Value Model

Files:

- Create: `engine/cash_value_model.py`
- Create: `engine/test_cash_value_model.py`
- Modify: `engine/log_pipeline.py`

Work:

1. Train two simple models first:
   - `cash_opportunity_model`: predicts positive effective cash delta
   - `cash_loss_model`: predicts avoidable negative effective cash delta
2. Start with logistic/ridge-style pure Python like the current `train_logistic_model`.
3. Export model JSON:
   - `cash_opportunity_model.json`
   - `cash_loss_model.json`
4. Add feature importance output.

Exit criteria:

- Model training is deterministic for the same input.
- Empty dataset returns a valid zero model.
- Top weighted features are inspectable.

### Phase 5: Policy Integration Behind a Flag

Files:

- Create: `engine/policy/learned_cash_value.py`
- Modify: `engine/policy/decision/purchase.py`
- Modify: `engine/policy/decision/movement.py`
- Modify: `engine/policy/decision/lap_reward.py`
- Modify: `engine/policy/decision/runtime_bridge.py`
- Modify: `engine/policy/factory.py`

Work:

1. Add `LearnedCashValueAdapter`.
2. Load model JSON only when `policy_mode` opts in, for example `heuristic_v3_engine_cashlearn`.
3. Convert current decision context into model features.
4. Apply small bounded score adjustments:
   - opportunity bonus clamp: `0.0..1.5`
   - loss penalty clamp: `-2.0..0.0`
5. Keep hard safety rules stronger than learned scores.

Exit criteria:

- Default `heuristic_v3_engine` is unchanged.
- `heuristic_v3_engine_cashlearn` can be compared in arena simulation.
- Learned model cannot override survival hard-blocks.

### Phase 6: Evaluation Gate

Files:

- Modify: `engine/compare_policies.py`
- Modify: `engine/simulate_with_logs.py`
- Create: `docs/current/ai/`

Work:

1. Compare baseline vs cashlearn over fixed seeds.
2. Track:
   - average rank
   - win rate
   - bankrupt_any_rate
   - average cash loss per game
   - top avoidable loss count
   - large opportunity miss count
3. Require improvement in at least one money metric without worse bankruptcy rate.
4. Store evidence under `docs/current/ai/evidence/`.

Exit criteria:

- No policy ships from one-off anecdotes.
- Every learned-policy change has a seed-stable comparison artifact.

## First Run

Initial command shape:

```bash
cd engine
python log_pipeline.py run --simulations 1000 --seed 20260507 --output-dir ../tmp/ai-cashlearn-baseline --policy-mode heuristic_v3_engine
```

Expected new outputs after Phase 1-2:

```text
tmp/ai-cashlearn-baseline/analysis/cash_events.jsonl
tmp/ai-cashlearn-baseline/analysis/top_cash_opportunities.json
tmp/ai-cashlearn-baseline/analysis/top_cash_losses.json
```

The first tuning discussion should start from the top 20 entries in:

- `top_cash_opportunities.json`
- `top_cash_losses.json`

## Non-Goals

- Do not train a neural network first.
- Do not replace the current heuristic policy in one step.
- Do not learn from hidden information unavailable to the acting player.
- Do not optimize only final win rate while increasing bankruptcies.
- Do not treat all cash gain as good. A cash gain that misses a finishing shard/coin line may be bad.

## Open Questions

1. Effective cash value should probably include tile/rent future value. Initial implementation should keep this conservative and explicit.
2. Some losses are intentionally accepted to win quickly. These need `won`, `turns_to_end`, and score trajectory context before being labeled as mistakes.
3. Human games may later become high-value data, but first model should train only on self-play simulations to avoid privacy and consent issues.
4. External AI traces may have different decision styles. Keep adapter/policy mode in the row schema.

## Immediate Next Step

Do not implement this cash-only plan as the main track. Start with `docs/superpowers/plans/2026-05-07-deep-rl-game-ai.md`.

The first implementation task is the RL reward contract. It should still include the cash event signals from this document, because large money gain/loss remains the first useful reward component.
