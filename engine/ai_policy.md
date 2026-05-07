# ai_policy.py

## 0.7.62 note
Control-profile scoring now more clearly favors growth follow-ups after a disruption window and recognizes profit-positive mark pressure separately from pure denial.

- 역할: 정책/휴리스틱 선택 로직을 제공한다.
- 최신 변경: 구매 가능성과 기대 구매가치를 계산할 때 `T2/T3` 고정 가격 대신 보드 위치별 가격표(`purchase_cost_for`)를 사용한다.
- 최신 변경: 지목 대상 선택은 더 이상 상대의 숨겨진 `current_character`를 직접 보지 않고, 공개 정보(내 캐릭터/이미 지난 턴 캐릭터/자객 공개 캐릭터)를 제외한 공개 추측 후보군에서만 고른다. 따라서 `mark_success_rate`는 실제 추측 적중률로 해석한다.
- 최신 변경: 모든 프로파일의 인물 선택 점수에 `피지목 리스크`를 반영한다. 현재 라운드 활성면에 자객/산적/추노꾼/박수/만신이 살아 있으면, 늦은 순번이면서 공개적으로 매력적인 인물(예: 중매꾼/객주/건설업자/사기꾼)이 감점된다.
- 최신 변경: 지목 대상 선택은 이제 `공개 후보군 점수 최대값 고정`이 아니라, 공개 후보 점수를 소프트맥스+균등 혼합 확률로 평탄화한 뒤 확률적으로 선택한다. 후보 점수는 확률 혼합으로 평탄화한 뒤 확률적으로 지목한다. 즉, 최고 점수 후보를 무조건 고정 선택하지 않아서 비현실적으로 높던 지목 적중률을 낮춘다.
- 최신 변경: 렌트 압박(rent corridor / 평균 렌트 요구액 / 추노꾼 강제이동 위험)을 공개 정보 기반으로 추정해, 모든 프로파일이 위기 시 파발꾼/탈출 노비/객주를 더 선호하고 중매꾼/건설업자/사기꾼 같은 성장형 인물은 덜 선호하도록 조정했다.
- 최신 변경: `SEVEN_TILES` 종료 규칙이 삭제되어, 리더 견제는 이제 `3구역 독점` 직전에 더 강하게 작동한다.
- 최신 변경: 상대 잔꾀 추론은 이제 **상대 손패 전부가 아니라 공개된 잔꾀만** 사용한다. 각 상대는 항상 1장의 비공개 잔꾀를 유지한다.
- 최신 변경: 정책은 비공개로 숨길 잔꾀 1장을 선택할 수 있고, 기본 휴리스틱은 짐/핵심 콤보 카드를 우선 숨긴다.
- 최신 변경: 박수/만신의 선택 휴리스틱에 **전역 짐 압력(public burden pressure)** 과 **보이는 짐 카드**를 반영한다. 이제 짐 카드가 여러 플레이어에게 공개되어 있고 보급까지 거리가 남아 있으면, 박수는 내 짐을 미리 넘겨 산불/화재 리스크를 피하는 인물로, 만신은 공개된 상대 짐을 미리 정리해 대형 손실을 줄이는 인물로 더 높은 점수를 받는다. 지목 대상 선택도 visible burden + 상대 현금을 더 강하게 본다.
- 최신 변경: `heuristic_v2_control`의 랩 보상은 여전히 조각 우선이지만, 저현금 + 렌트/짐/유동성 리스크가 겹치면 현금을 다시 고르는 안전장치를 강화했다. 따라서 leader emergency가 높아도 post-reserve 현금이 크게 마이너스이거나 짐 정리 압력이 쌓이면 cash로 후퇴할 수 있다.
- 최신 변경: 이제 정책은 **범용 생존 점수(generic survival score)** 를 공통 축으로 계산한다. 이 값은 유동성 reserve, 렌트 압박, 즉사 확률, 짐 정리 압력, 시작점/F/S 접근성을 묶어 산출하며, 인물 선택 / 잔꾀 사용·보상 선택 / 주사위 카드 이동 선택 / 랩 보상 선택이 모두 이 축을 함께 참고한다.
- 최신 변경: 범용 생존 점수가 위기 구간이면 성장형 인물(중매꾼/건설업자/사기꾼)은 현재 운용 가능 현금이 부족할 때 강하게 감점되고, 탈출 노비/파발꾼/객주와 저현금 기능형(자객/아전/만신)은 가산된다. 즉 **살아남을 수 없는 성장 선택** 을 하드하게 눌러 준다.
- 최신 변경: 잔꾀/주사위 카드/랩 보상도 같은 생존 축을 공유한다. 위기 구간이면 건강 검진/우대권/저속 같은 방어성 선택과 시작점/F/S 진입 동선, 현금 보상이 더 강하게 선호되고, 무료 증정/마당발 같은 성장 선택은 뒤로 밀린다.
- 최신 변경: 초기 보상 선택은 랩 보상과 같은 allocation 결정 객체를 재사용하되 `GameRules.start_reward` 예산/풀을 읽고 기본 정책은 현금 우선으로 선택한다.
- 최신 변경: 범용 생존 점수는 이제 **공개정보 기반 2턴 위험**까지 본다. 앞쪽 타일의 적 소유 밀도/최대 비용, 공개된 잔꾀, 활성면의 돈을 빼앗는 인물(탐관오리/산적/아전/추노꾼/짐이 있는 상태의 만신), 전체 플레이어 현금 분포를 함께 묶어 `money_distress`, `two_turn_lethal_prob`, `controller_need`를 계산한다.
- 최신 변경: 돈이 부족한 상황에서는 단순 절약이 아니라 **상황 타개 행동**을 우선한다. 인물 선택은 객주/아전/만신/탈출 노비 같은 저현금 기능형 또는 돈벌이/탈출형을 더 선호하고, 타일 구매는 미루며, 감독관(교리 연구관/교리 감독관)은 활성화된 돈 압박 인물을 끄는 방향으로 가산된다. 또한 연구관/감독관의 턴 시작 액티브로 자신(또는 team_id가 있는 모드에선 팀원)의 짐 카드 1장을 제거하는 행동을 고려한다.
- 주의: 가격 실험을 바꿀 때 엔진과 같은 조회 경로를 써야 정책-엔진 불일치가 생기지 않는다.
- 수정 규칙: 대응 소스 수정 시 반드시 본 문서를 같이 갱신하고 mtime이 소스보다 늦어야 한다.

## ArenaPolicy
- 혼합 정책 아레나 실행용 래퍼 정책이다.
- 기본 라인업은 `heuristic_v1`, `heuristic_v2_token_opt`, `heuristic_v2_control`, `heuristic_v2_balanced` 이다.
- 플레이어별 캐릭터/랩 정책을 라우팅하고 디버그 선택도 해당 하위 정책에서 회수한다.

- v0.7.26: Added liquidity-risk metrics (`expected_loss`, `worst_loss`, `reserve`) from visible next-turn threats. These metrics now influence v2 character scoring and heuristic purchase decisions. Escape / burden-insurance characters gain value under cash pressure; expansion characters are penalized when reserves would be violated.

- v0.7.26 note: ArenaPolicy delegates risk-aware purchase decisions to each per-player heuristic policy.

- v0.7.26 note: ArenaPolicy delegates all purchase/draft/mark decisions to per-player heuristic policies, including the new liquidity-aware purchase gate.


## Monopoly-aware update (v0.7.26)
- Expansion characters (중매꾼/건설업자) gain extra value when they can finish a block monopoly soon.
- Mobility characters (객주/파발꾼/탈출 노비) gain value when they can route into claimable monopoly blocks or escape enemy monopoly pressure.
- Disruption characters (사기꾼/추노꾼/자객/산적) gain extra value when an enemy is one tile away from monopoly.
- Purchase decisions now preserve monopoly-blocking buys that prevent an opponent from completing a monopoly.
- Trick use scoring boosts movement/purchase tricks when they help finish or deny monopolies.

- 최신 변경: `사기꾼`은 탈취 타일의 승점 코인까지 같이 가져오기 때문에, AI는 탈취 가능한 타일에 쌓인 승점 코인 수와 독점 저지/완성 가치까지 함께 평가한다.


## v0.7.28 refactor note
- Mark-guess constants, public guess filtering, exposure weighting, and mark probability mixing were extracted into dedicated policy utility modules (`policy_groups.py`, `policy_mark_utils.py`).
- `ai_policy.py` now delegates pure helper logic to those modules, making the main policy file easier to navigate without changing behavior.



## 0.7.50 update
- BasePolicy now exposes hook registration for before/after `choose_*` decisions.
- HeuristicPolicy and ArenaPolicy inherit the hook-capable base state, and engine logging can subscribe without changing decision code.

- v0.7.56: control retuned toward mark-profit conversion, token_opt retuned toward placement execution and movement/card timing.

- 0.7.56: control now prefers profitable mark lines; token_opt now values revisit windows and token placement execution.


## Rule injection note
AI now reads token/end thresholds primarily through `state.config.rules` so policy evaluation can follow injected rulesets.


## 0.7.60 note
AI evaluations now reference injected rule values for rent/malicious costs and dice-card counts where available.


## Validation hotfix note
- Restored `choose_geo_bonus()` implementation for runtime simulation validation.
- Geo bonus now keeps the prior cash/shard/coin bias and also references public-info survival context (`money_distress`, `two_turn_lethal_prob`, `controller_need`, `own_burden_cost`).

- F 진행은 이제 **리더 전용 가속 전략**으로 취급한다. 비리더는 기본적으로 F1/F2 landing 가치가 낮거나 음수이며, 주사위 카드로 F를 맞추는 선택에는 추가 페널티가 붙는다.
- `HeuristicPolicy`는 `_board_race_score()`, `_race_position_context()`, `_f_progress_context()`를 사용해 현재 선두/추격 관계와 남은 F 종료 여유를 해석한다.
- `choose_movement()`, `choose_lap_reward()`, `choose_geo_bonus()`에서 공통 F 컨텍스트를 참조하며, 비리더는 shard 2개(F2)만 보고 카드를 태우지 않도록 억제한다.


## v7.61 fleader hotfix
- `_race_position_context()` now safely handles dead/non-participating players during passive decision evaluation.


## 최근 메모
- 사기꾼 인수 시도는 이제 정책의 생존 게이트를 통과할 때만 실행된다. 요구 비용을 지불한 뒤에도 2턴 생존 reserve를 유지해야 하며, 고가 인수선(대략 20~24+)은 리더 마감권이 아니면 차단한다.


## 공용 생존 모듈 연동
- `survival_common.py`를 통해 공통 생존 신호(`reserve`, `money_distress`, `two_turn_lethal_prob`, cleanup 비용)를 표준 구조로 변환한다.
- 액션 생존 가드와 사기꾼 인수 가드는 `ai_policy.py` 내부에서 직접 임계값을 중복 구현하지 않고 `survival_common.py`의 공용 함수로 위임한다.
- 목적은 생존 관련 규칙을 한 곳에서 관리하고, 구매/사기/이동/잔꾀 판단이 같은 원칙을 공유하도록 만드는 것이다.


## Update note
- character selection now consumes survival advice from survival_common as a policy input.
- survival can emit a hard-block hint for true-suicide growth picks. When a non-blocked alternative exists, draft/final-character selection now removes the hard-blocked candidate from the final choice pool instead of merely subtracting score.


## Update note
- survival advice is policy-owned with hard-block hints for true suicides.

- policy now consumes survival advice (severity/bias/hard-block hint) before final character choice.

- v7.61 perf patch: cached board-control, race, and movement-eval snapshots to reduce repeated draft-scoring work.


- 최신 AI 조정: 건설업자는 조각 소모 없이 무료 건설로 평가한다.

- 2026-03-26: cleanup risk model now keeps next-draw, two-draw, and full-cycle probabilities in AI burden evaluation; end-turn cash checks use probabilistic cleanup exposure instead of worst-case-only assumptions.


- 2026-03-27 audit hotfix: `choose_draft_card()` / `choose_final_character()` now treat `survival_hard_block` as a true veto when any safe alternative exists. Previously the hint only applied a very large negative score, which still left a blocked growth pick in the candidate pool.

- 2026-03-27 auditfix2: `heuristic_v3_engine` now treats cleanup/reserve distress more conservatively. Under visible cleanup pressure or reserve shortfall, growth picks (`중매꾼`/`건설업자`/`사기꾼`) lose more value, cash lap rewards become more dominant, and non-blocking land buys are rejected earlier when survival cash or token-window lines are superior.


## v7.61 v3 Engine strategic patch notes
- heuristic_v3_engine now models early turn-order land races for 어사/탐관오리.
- 박수 shard checkpoints are treated as stability thresholds (5 online, 7 very stable).
- heuristic_v3_engine lap reward and purchase logic now recognize 박수 shard checkpoints and safer low-cost T3 conversions.

- v3_engine now leans further into early land-race openers and safer T3 conversion windows while preserving 박수 shard-checkpoint stability.

- v3_engine now biases further toward safe expansion windows and coin conversion when placeable own-tile token windows are open.

- v3_engine now inherits token-engine-heavy finishing priorities in safe states, with earlier coin conversion and a weaker token-window veto.

- heuristic_v3_engine memo: intended to value 아전 burst timing when enemy pawns stack on enemy-owned tiles and intended to value 객주 lap-engine timing near board end when mobility tricks/dice can chain lap rewards.

- Winpush3 intent: after core shard checkpoints, v3_engine should convert more aggressively into safe growth/coin scoring; favor lap-engine windows for 객주 and allow low-risk T2/T3 buys instead of over-hoarding shards.

- 2026-04-15 follow-up: survival hard-blocking now only treats pure expansion faces (`중매꾼`/`건설업자`/`사기꾼`) as true growth veto candidates, while `박수` reserve relief uses the 5-shard online checkpoint consistently with purchase exceptions.
