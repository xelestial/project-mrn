# EXAMPLE Trick Card Source Snapshot

이 파일은 **유효한 잔꾀 정보 문서가 아닙니다**.

목적:
- 현재 소스코드가 잔꾀를 어떻게 보고 있는지 보여주는 예시 스냅샷
- 구조 설계와 검토용 참고

이 파일을 authoritative trick data로 사용하면 안 되는 이유:
- 카드 텍스트의 전체 의미를 완전하게 표현하지 않습니다
- 타이밍/창(window)/도착 후 처리/보류형 카드 성격을 생략합니다
- 실제 게임 규칙 문서가 아니라 현재 코드 분기 요약입니다
- 장기적으로는 별도 구조화 메타데이터가 필요합니다

## 현재 소스 스냅샷 기준 카드 목록

형식:
- `장수 | 이름 | 현재 분류 | 현재 소스코드 처리`

### 직접 효과 또는 상태 플래그
- `1 | 성물 수집가 | turn_buff | extra_shard_gain_this_turn += 1`
- `1 | 건강 검진 | global_rent_half | state.global_rent_half_this_turn = True`
- `1 | 우대권 | rent_waiver | rent_waiver_count_this_turn += 1`
- `1 | 뇌고왕 | personal_rent_half | trick_personal_rent_half_this_turn = True`
- `1 | 뇌절왕 | zone_chain | trick_zone_chain_this_turn = True`
- `1 | 무료 증정 | free_purchase | trick_free_purchase_this_turn = True`
- `1 | 신의뜻 | same_tile_shard_rake | trick_same_tile_shard_rake_this_turn = True`
- `1 | 가벼운 분리불안 | same_tile_cash2 | trick_same_tile_cash2_this_turn = True`
- `1 | 마당발 | extra_adjacent_buy | trick_one_extra_adjacent_buy_this_turn = True`
- `1 | 도움 닫기 | encounter_boost | trick_encounter_boost_this_turn = True`
- `1 | 극심한 분리불안 | forced_arrival | 가장 먼 플레이어 위치로 즉시 도착`
- `1 | 번뜩임 | trick_exchange | 잔꾀 교환`
- `1 | 재뿌리기 | tile_rent_zero | 특정 토지 통행료 0`
- `1 | 긴장감 조성 | tile_rent_double | 특정 토지 통행료 2배`
- `1 | 느슨함 혐오자 | global_rent_double | 이번 턴 전역 통행료 2배`
- `1 | 극도의 느슨함 혐오자 | permanent_rent_double | 영구 전역 통행료 2배`
- `1 | 과속 | buy_extra_die | cash -2, dice +1`
- `1 | 저속 | sell_die | cash +2, dice -1`
- `1 | 이럇! | all_extra_die | 생존자 전원 dice +1`
- `2 | 아주 큰 화목 난로 | shard_and_f | shards +1, F +1`
- `2 | 거대한 산불 | shard_and_f | shards +2, F +2`
- `1 | 무역의 선물 | tile_swap | 자기 토지/상대 토지 교환`

### 일반 잔꾀 단계 보류형
- `1 | 강제 매각 | held_anytime | 일반 잔꾀 단계에서는 즉시 처리하지 않음`
- `1 | 뭘리권 | held_anytime | 일반 잔꾀 단계에서는 즉시 처리하지 않음`
- `1 | 뭔칙휜 | held_anytime | 일반 잔꾀 단계에서는 즉시 처리하지 않음`
- `1 | 호객꾼 | held_anytime | 일반 잔꾀 단계에서는 즉시 처리하지 않음`

### burden
- `8 | 무거운 짐 | burden | 사용 시 4냥 지불 후 제거`
- `8 | 가벼운 짐 | burden | 사용 시 2냥 지불 후 제거`

## 현재 소스가 전제하는 추가 규칙 예시

- 손패가 있으면 공개되지 않은 잔꾀는 항상 1장만 존재합니다.
- `언제나 사용 가능` 판정은 설명 문자열 기반입니다.
- 일반 잔꾀는 자신의 턴에 1장만 사용합니다.
- 언제나 잔꾀는 자신의 턴 잔꾀 단계에서 여러 장 사용할 수 있습니다.
- 보급 시 burden 교환 여부는 별도 정책 판단을 거칩니다.

## 왜 이 파일을 `EXAMPLE`로 남기나

이 파일은 “현재 코드가 이렇게 분기한다”는 예시일 뿐입니다.

부족한 점:
- 공개/비공개 규칙이 단순 표로 다 표현되지 않음
- 도착/말/효과 타이밍 차이를 완전하게 모델링하지 않음
- 카드가 실제로 어느 시점에 UI prompt를 열어야 하는지 표현하지 않음
- 향후 파이프라인/노드 구조로 옮길 때 더 세분화된 메타가 필요함

따라서 실제 검토 기준은 이 파일이 아니라:
- `DATA/GPT_TRICK_CARD_RUNTIME_GUIDE.md`
- 그리고 실제 소스파일들
을 함께 봐야 합니다.
