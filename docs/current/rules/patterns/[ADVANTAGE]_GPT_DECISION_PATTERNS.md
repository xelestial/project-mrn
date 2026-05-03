# GPT Advantage Patterns

## Purpose
- 실제 샘플 점검 중 “합리적이거나 유지할 가치가 있는” 선택 원칙을 모아둔 문서
- 전략 튜닝 시 가산점 규칙, intent bias, veto 예외의 기준선으로 사용

## Core Principles
- 캐릭터의 강점과 행동이 일치해야 한다.
- 지금 써서 얻는 가치가 보존 가치보다 클 때만 카드/잔꾀를 쓴다.
- 생존선 아래에서는 성장보다 생존을 우선한다.
- 같은 턴과 다음 턴의 선택은 같은 plan/intention을 공유해야 한다.

## Character-Aligned Advantages
- `객주`
  - 랩, F 도착, 자기 타일 재방문, token/coin 재활용이 핵심 가치다.
  - 일반 빈땅 하나를 위해 고급 이동 카드 2장을 쓰지 않는다.
  - `cross_start`, `land_f`, `token_window`, `rich_pool`이 열릴 때 이동 자원을 집중한다.
- `박수`
  - burden/cleanup/shard checkpoint 문제를 해결하는 쪽이 핵심이다.
  - `shards >= 5`이고 `T3 저가 매수`일 때는 생존 예외로 구매를 열 수 있다.
  - 랩보상도 `cash only`로 단순 회귀하지 말고 shard/checkpoint 문맥과 이어져야 한다.
- `교리 연구관/감독관`
  - burden 관리와 성장의 균형이 핵심이다.
  - 교리 완화는 “자기 자신 우선”이 아니라 가장 위험한 플레이어를 먼저 안정화해야 한다.
- `객주/파발꾼/탈출 노비`
  - 이동 자원은 일반 확장보다 랩, 재방문, 회피, 정밀 착지에 우선 배분한다.

## Resource Preservation Advantages
- 초반은 빈땅 기대값이 높지만, 동시에 카드 없이도 먹을 수 있는 구간이다.
- 따라서 초반 카드 소비는 아래 조건에서만 강화한다.
  - `T3`, 블록 연결, monopoly 압박
  - 랩/F 도착
  - 자기 타일 재방문
  - 즉시 생존 회피
- 조건부 잔꾀는 실제 창이 있을 때만 사용한다.
  - `성물 수집가`: shard/F/lap 기회가 있을 때
  - `도움닫기`: 실제 조우/추가 전진 창이 있을 때
  - `뇌절왕`: own-tile chain 또는 추가 이동 가치가 있을 때
  - `저속`: 단거리 frontier가 더 좋거나 생존 현금이 필요할 때

## Survival / Cleanup Advantages
- `cleanup_pressure`, `money_distress`, `two_turn_lethal_prob`가 높으면 성장 구매를 막는다.
- burden이 많은 상태에선
  - 즉시 비용이 있는 트릭을 더 보수적으로 보고
  - cash floor를 더 높게 잡는다.
- `박수`의 온라인 예외는 일반 성장 예외가 아니라 burden/cleanup 생존 예외다.

## Mark / Control Advantages
- 지목은 반드시 해야 하되, 불가능한 캐릭터를 후보로 넣지 않는다.
- mark/control 계열은 공개 정보와 turn-order 제약을 만족하는 후보 안에서만 추정한다.
- fallback 가치가 낮으면 공격형 지목보다 생존/회피 쪽 가중을 우선한다.

## Runtime Rules Worth Keeping
- helper/traits/runtime bridge를 통해 live path가 같은 규칙을 공유하도록 유지한다.
- runtime decision은 아래 입력을 우선 신뢰한다.
  - `PolicySurvivalContext`
  - `TurnPlanContext`
  - `character_traits`
  - `decision helper`

## Near-Term Tuning Targets
- `객주`의 랩 엔진 집중도 강화
- `박수`의 shard/checkpoint follow-up 일관성 강화
- burden/cleanup 위험 상태에서의 카드 보존 우선도 강화
- 창 없는 조건부 잔꾀 사용 추가 억제

## 2026-04-03 Run Snapshot Additions (100 games)
- `턴당 1장 잔꾀` 규칙 하에서, “한 장으로 턴 목적을 분명히 만드는 선택”이 안정적이다.
  - 같은 턴에 여러 잔꾀를 섞는 경로가 사라지면서 계획 일관성이 개선됨.
- burden 은닉 우선(`hide_burden_first`)은 여전히 유효한 안전 전략이다.
  - 초반 공개 리스크와 강제 정리 비용을 동시에 줄여 생존선 유지에 기여.
- `뭘리권/뭔칙휜`은 사전 사용 후 이동 결정 단계에서 재굴림 예산으로 쓰는 방식이 유효하다.
  - 카드 소비는 1회로 제한하면서도 이동 품질 개선을 얻는다.
- `호객꾼`은 병목 구간에서 선점한 경우 수비 가치가 생긴다.
  - 상대 이동이 `obstacle_slowdown`으로 감소해 렌트/도착 타이밍 제어에 도움됨.
- `언제나 잔꾀` 메타 제거 후에는 턴 목적-카드 선택 정렬이 더 명확해진다.
  - `regular_tricks_used`만 집계되고 `anytime_tricks_used=0`이 안정적으로 유지된다.
