# Engine Stupid Patterns

## Purpose
- 실제 로그 점검 중 반복해서 확인된 “명백한 바보수”를 정리한 문서
- veto rule, regression test, scenario parity test의 기준선으로 사용

## Core Definition
- 캐릭터 강점과 반대로 행동하는 선택
- 현재 공개 정보만으로도 기대값이 낮은데 자원을 태우는 선택
- 같은 plan을 유지하지 못하고 턴마다 다른 사람이 조종하는 것처럼 보이는 선택
- 생존선 아래에서 공격/성장을 우선하는 선택

## Confirmed Bad Patterns
- `객주`가 초반 빈땅 하나를 위해 `2+3` 같은 이동 카드 2장을 쓰는 선택
  - 랩/F/재방문 엔진 자원을 일반 매수에 소모하는 패턴
- `성물 수집가`를 shard 획득 창 없이 쓰는 선택
  - F/lap/shard gain이 없는 턴에 허공에 버리는 패턴
- `도움닫기`를 실제 조우 가능성 없이 쓰는 선택
  - 만날 말도 없는데 조건부 이동 카드를 미리 버리는 패턴
- `뇌절왕`을 own-tile chain 없이 쓰는 선택
  - 첫 턴이나 own-tile 부재 상태에서 value가 거의 없는 사용
- `저속`을 단거리 frontier 이점 없이 쓰는 선택
  - 생존 현금도 안 급한데 속도만 깎는 패턴

## Survival Failures
- 현금이 낮은 상태에서 위험 텔포/이동을 눌러 렌트를 연속으로 맞는 선택
  - 대표 예: “위험 텔포 + 기본 이동”으로 한 턴에 렌트 2회
- burden/cleanup 압박이 큰데 일반 성장 구매를 계속하는 선택
- `박수`로 burden/shard 맥락을 열어놓고 바로 다음 랩보상을 `cash only`로 회귀하는 선택

## Global Effect Misuse
- 초반 저자산 상태에서 전역 렌트 2배를 켜는 선택
  - `극도의 느슨함 혐오자`를 리더 견제 문맥 없이 사용해 자기 목을 조르는 패턴
- 내가 보드 우위도 아니고 현금 버퍼도 없는데 global pressure card를 먼저 켜는 선택

## Draft / Character Mismatch
- 캐릭터를 고른 이유가 다음 선택과 이어지지 않는 패턴
  - 캐릭터 선택은 A 논리
  - 이동은 B 논리
  - 트릭은 C 논리
  - 랩보상은 D 논리
- 같은 2턴 묶음 안에서
  - 1턴은 “가속”
  - 2턴은 “저속”
  처럼 plan signal이 충돌하는 패턴

## Mark / Doctrine Errors
- 자기보다 앞선 priority 캐릭터를 지목 후보로 상정하는 선택
- 교리 완화를 `자기 자신 아니면 첫 후보`로 단순 처리하는 선택
- distress, burden, cleanup 위험을 무시하고 완화 대상을 고르는 선택

## Runtime Regression Patterns
- helper는 존재하지만 live path에 window/signal을 넘기지 않아 규칙이 죽는 패턴
- 깨진 문자열 비교 때문에 trait/exception이 발동하지 않는 패턴
- helper 단위 테스트만 통과하고 runtime branch parity는 깨지는 패턴

## Must-Block Rules
- `객주` + generic unowned tile + two-card move -> 강한 패널티 또는 veto
- `성물 수집가` + no shard window -> veto
- `도움닫기` + no forward encounter window -> veto
- `뇌절왕` + no own-tile chain window -> veto
- `저속` + no short-range frontier edge + no survival urgency -> veto
- `박수` 예외는 helper-based trait check로만 판정
- doctrine relief는 distress scoring 기반으로만 선택

## Regression Test Targets
- `박수` cleanup 예외가 live purchase path에서 실제로 열리는가
- trick preserve rules가 runtime window signal을 실제로 받는가
- doctrine relief가 가장 위험한 후보를 고르는가
- help-run window가 조우 가능성 없이 열리지 않는가

## 2026-04-03 Run Snapshot Additions (100 games)
- `호객꾼`을 병목이 아닌 구간에서 늦게 쓰는 선택
  - 상대 경로를 거의 건드리지 못해 1장 자원을 공중에 버리는 패턴.
- 지목 실패(`mark_fail_no_target`)가 반복되는 라운드 운영
  - 공격 캐릭터를 고르고도 실질 타겟이 없어 턴 가치가 떨어지는 패턴.
- burden 정리 압박을 무시한 현금 소모형 운영
  - `_default_fortune_burden_cleanup` 기인 파산 비중이 높게 남는 패턴.
- 랩 보상을 현금 일변도로 고정하는 선택
  - 토지/승점 전환 타이밍을 놓쳐 후반 점수 추격력이 약해지는 패턴.
- 제거된 `언제나` 규칙을 전제로 카드 우선순위를 짜는 선택
  - 실제 엔진은 `턴당 1장`이므로, 다중 연쇄 사용 기대를 둔 의사결정은 무가치 패턴.
