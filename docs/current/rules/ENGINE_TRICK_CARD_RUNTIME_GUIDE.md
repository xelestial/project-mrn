# Engine Trick Card Runtime Guide

이 문서는 현재 `engine/` 소스코드가 잔꾀 카드를 실제로 어떻게 처리하는지 정리한 문서다.

중요:
- 이 문서는 카드 설명문 요약이 아니라 `현재 소스 구현` 설명이다.
- 카드 설명문과 구현이 다르면, 이 문서는 `현재 구현`을 우선해 적는다.
- 현재 규칙 기준으로 `언제나 사용`은 제거되었고, `TrickCard.is_anytime`는 항상 `False`다.

기준 소스:
- [engine/trick.csv](/Users/sil/Workspace/project-mrn/engine/trick.csv)
- [engine/trick_cards.py](/Users/sil/Workspace/project-mrn/engine/trick_cards.py)
- [engine/state.py](/Users/sil/Workspace/project-mrn/engine/state.py)
- [engine/engine.py](/Users/sil/Workspace/project-mrn/engine/engine.py)
- [engine/effect_handlers.py](/Users/sil/Workspace/project-mrn/engine/effect_handlers.py)

## 1. 기본 구조

현재 구조는 다음 순서로 동작한다.

1. [engine/trick.csv](/Users/sil/Workspace/project-mrn/engine/trick.csv)에서 카드 이름, 설명, 매수 정보를 읽는다.
2. [engine/trick_cards.py](/Users/sil/Workspace/project-mrn/engine/trick_cards.py)가 이를 `TrickCard` 객체로 만든다.
3. [engine/state.py](/Users/sil/Workspace/project-mrn/engine/state.py)의 `PlayerState.trick_hand`가 실제 손패를 가진다.
4. [engine/engine.py](/Users/sil/Workspace/project-mrn/engine/engine.py)가
   - 잔꾀 공개/비공개 처리
   - 자신의 턴 잔꾀 단계
   - 재굴림 예산(뭘리권/뭔칙휜) 처리
   - 강제 매각/도착 트리거
   - 보급 시 burden 교환
   를 관리한다.
5. [engine/effect_handlers.py](/Users/sil/Workspace/project-mrn/engine/effect_handlers.py)의 `handle_trick_card(...)`가 각 카드의 직접 효과를 처리한다.

## 2. 공개 / 비공개 처리

현재 잔꾀 공개 규칙은 매우 단순하다.

- 손패가 0장이면 비공개 카드 수는 `0`
- 손패가 1장 이상이면 비공개 카드 수는 항상 `1`
- 나머지 카드는 공개 카드다

관련 구현:
- [engine/state.py](/Users/sil/Workspace/project-mrn/engine/state.py)의 `public_trick_cards()`
- [engine/state.py](/Users/sil/Workspace/project-mrn/engine/state.py)의 `hidden_trick_count()`
- [engine/engine.py](/Users/sil/Workspace/project-mrn/engine/engine.py)의 `_sync_trick_visibility(...)`

실제 동작:
- `hidden_trick_deck_index` 1장만 숨김 처리한다.
- 정책이 `choose_hidden_trick_card(...)`를 제공하면 그 카드가 숨겨진다.
- 정책이 없거나 유효하지 않으면 엔진이 손패 중 1장을 무작위로 숨긴다.

## 3. 잔꾀 사용 시점(현재 규칙)

`언제나 사용` 규칙은 제거되었다.

- `TrickCard.is_anytime`는 항상 `False`
- 잔꾀는 자신의 턴에서 `trick_to_use` 1회 선택으로만 사용
- `뭘리권/뭔칙휜`은 별도 연속 사용이 아니라, 1장 사용 후 이동 굴림에서 재굴림 예산으로 동작
- `강제 매각/뇌절왕`도 동일하게 턴 잔꾀 단계에서 “미리 사용”해야 효과가 켜진다

관련 구현:
- [engine/trick_cards.py](/Users/sil/Workspace/project-mrn/engine/trick_cards.py)
- [engine/engine.py](/Users/sil/Workspace/project-mrn/engine/engine.py)의 `_use_trick_phase(...)`, `_try_anytime_rerolls(...)`

주의:
- 아래 카드별 상세에서 `is_anytime` 표기가 남아 있더라도, 최신 규칙 기준 해석은 모두 `아니오`다.

관련 구현:
- [engine/engine.py](/Users/sil/Workspace/project-mrn/engine/engine.py)의 `_use_trick_phase(...)`

## 4. 상태 플래그 / 상태 변수의 정확한 의미

아래는 현재 소스에서 실제로 쓰는 잔꾀 관련 상태 변수다.

### `extra_shard_gain_this_turn`
- 설정 카드: `성물 수집가`
- 설정 방식: `player.extra_shard_gain_this_turn += 1`
- 리셋 시점: 라운드 시작
- 현재 소비처: `landing.f.resolve`에서 F1/F2 획득 조각 배수 처리
- 의미 요약:
  - 이번 턴 F칸 조각 획득량에 배수(2배)로 반영된다
  - 즉 현재 소스 기준으로는 `실효성이 불명확하거나 미완성`인 상태다

### `rent_waiver_count_this_turn`
- 설정 카드: `우대권`
- 설정 방식: `+1`
- 소비 시점:
  - 일반 렌트 지불 처리에서 1회 소모
  - `사기꾼` 강탈형 렌트 계산에서도 1회 소모
- 실제 동작:
  - 값이 1 이상이면 해당 렌트 비용을 `0`으로 만들고 `1` 감소시킨다
- 의미 요약:
  - “이번 턴 통행료를 1회 내지 않는다”가 정확하다

### `trick_free_purchase_this_turn`
- 설정 카드: `무료 증정`
- 설정 방식: `True`
- 소비 시점:
  - 구매 시도 함수에서 비용 계산 직후 바로 `False`로 리셋
- 실제 동작:
  - 해당 구매 시도에서 구매 비용을 `0`으로 만든다
- 주의:
  - 구매를 실제로 성공하지 못해도, 구매 시도에 들어간 순간 플래그가 꺼진다
  - 즉 “성공 시 1회 무료”가 아니라 “구매 시도 1회 무료”에 가깝다

### `trick_dice_delta_this_turn`
- 설정 카드:
  - `과속`: `+1`
  - `저속`: `-1`
  - `이럇!`: 살아 있는 모든 플레이어에게 `+1`
- 소비 시점:
  - 이동 굴림 직전 기본 주사위 개수 계산에 합산
- 리셋 시점:
  - 라운드 시작
  - 실제 이동 처리 후에도 `0`으로 정리되는 흐름이 있다
- 의미 요약:
  - 이번 턴의 주사위 개수 보정값이다

### `trick_personal_rent_half_this_turn`
- 설정 카드: `뇌고왕`
- 설정 방식: `True`
- 소비 시점:
  - 렌트 계산 함수 `_effective_rent(...)`
- 실제 동작:
  - `payer`가 이 플래그를 갖고 있으면 렌트를 한 번 `// 2`
  - `owner`가 이 플래그를 갖고 있어도 렌트를 한 번 `// 2`
- 의미 요약:
  - 설명문대로 “내가 내는 통행료/받는 통행료 절반”을 구현하려고 한 형태다
  - 양쪽 모두 플래그가 있으면 두 번 나뉘므로 결과적으로 `1/4`까지 줄어들 수 있다

### `trick_same_tile_cash2_this_turn`
- 설정 카드: `가벼운 분리불안`
- 설정 방식: `True`
- 소비 시점:
  - 미소유 타일 도착 후 처리
  - 자기 타일 도착 후 처리
  - 렌트 지불 후 처리
- 실제 동작:
  - 최종 도착 칸에 `나 말고 살아 있는 플레이어`가 함께 있으면
  - 그 수만큼 `2 * len(co)` 현금을 즉시 얻는다
- 주의:
  - 1회 소모가 아니다
  - 라운드 시작까지 플래그가 유지되므로, 같은 턴의 여러 도착 이벤트에서 반복 적용될 수 있다

### `trick_same_tile_shard_rake_this_turn`
- 설정 카드: `신의뜻`
- 설정 방식: `True`
- 소비 시점:
  - 미소유 타일 도착 후 처리
  - 자기 타일 도착 후 처리
  - 렌트 지불 후 처리
- 실제 동작:
  - 최종 도착 칸에 `나 말고 살아 있는 플레이어`가 함께 있으면
  - 각 상대의 현재 shard 수만큼 비용을 그 상대에게 청구한다
  - `_pay_or_bankrupt(...)` 결과가 `paid=True`인 금액만 합산한다
  - 로그에는 `{total, details}` 구조로 남는다
- 주의:
  - 이것도 1회 소모가 아니다
  - 라운드 시작까지 유지된다

### `trick_one_extra_adjacent_buy_this_turn`
- 설정 카드: `마당발`
- 설정 방식: `True`
- 소비 시점:
  - 미소유 타일을 정상 구매한 직후
  - 자기 타일 도착 직후
  - 렌트 지불 성공 직후
- 실제 동작:
  - 현재 위치 기준 같은 블록의 인접 타일 1개를 추가 매수 시도한다
- 리셋:
  - 실제 위 분기 중 하나에 들어가면 `False`로 꺼진다
- 주의:
  - 미소유 타일에 도착했지만 구매가 실패/스킵이면 그 자리에서는 꺼지지 않는다
  - 즉 “다음 유효 도착 이벤트”까지 들고 갈 수 있다

### `trick_encounter_boost_this_turn`
- 설정 카드: `도움 닫기`
- 설정 방식: `True`
- 소비 시점:
  - 이번 이동 처리 중 경로를 따라가며 다른 말과 실제로 만났는지 확인할 때
- 실제 동작:
  - 이동값 `move > 0`일 때
  - 시작칸과 최종도착칸 사이의 중간 칸들을 순서대로 보면서
  - 다른 살아 있는 플레이어의 말이 있는 첫 칸을 만나면
  - 즉시 `1d6 + 1d6`을 추가 굴려 총 이동량에 더한다
- 리셋:
  - 그 이동 처리 끝에 무조건 `False`
- 의미 요약:
  - “같은 칸 조우 시 추가 2d6”이 아니라
  - `이동 도중 중간 경로에서 처음 만나는 말` 1회만 체크한다

### `trick_force_sale_landing_this_turn`
- 선언은 되어 있다
- 라운드 시작에 `False`로 리셋된다
- 현재 검색 기준 설정/소비하는 활성 코드가 없다
- 의미 요약:
  - 현재는 사실상 미사용 변수다

### `trick_zone_chain_this_turn`
- 설정 카드: `뇌절왕`
- 설정 방식: `True`
- 라운드 시작에 리셋된다
- 현재 검색 기준 소비하는 활성 코드가 없다
- 중요:
  - 실제 연쇄 이동 처리 코드는 이 플래그를 보지 않는다
  - 활성 코드는 `손패에 아직 "뇌절왕" 카드가 남아 있는지`를 직접 확인한 뒤, 도착 시점에 카드를 소비한다
- 의미 요약:
  - 현재 구현에선 `플래그 방식`과 `실제 활성 처리 방식`이 어긋나 있다

### `global_rent_half_this_turn`
- 설정 카드: `건강 검진`
- 소비 시점: 렌트 계산
- 실제 동작: 전체 렌트 계산 결과를 `ceil(rent / 2)` 처리

### `global_rent_double_this_turn`
- 설정 카드: `느슨함 혐오자`
- 소비 시점: 렌트 계산
- 실제 동작: 이번 라운드 렌트를 2배

### `global_rent_double_permanent`
- 설정 카드: `극도의 느슨함 혐오자`
- 소비 시점: 렌트 계산
- 실제 동작: 이후 계속 렌트를 2배

### `tile_rent_modifiers_this_turn[pos]`
- 설정 카드:
  - `재뿌리기`: 해당 타일 `0`
  - `긴장감 조성`: 해당 타일 `max(2, 기존값 * 2)`
- 소비 시점: `_effective_rent(...)`
- 실제 동작:
  - 타일별 일시 렌트 배율
  - 라운드 시작 시 초기화

## 5. 카드별 현재 처리

아래는 카드별 현재 구현이다.

### 성물 수집가
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.extra_shard_gain_this_turn += 1`
  - 반환 타입: `TURN_BUFF`
- 주의:
  - 현재 활성 소비처를 찾지 못했다
  - 즉 `버프 플래그만 세우고 실제 shard 추가가 연결되지 않은 상태`로 보인다

### 무거운 짐
- 매수: 8
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 현금 `4`가 있으면 `4` 지불 후 버린다
  - 부족하면 실패
- 보급:
  - 보급 시 `4`를 내고 교환 가능

### 가벼운 짐
- 매수: 8
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 현금 `2`가 있으면 `2` 지불 후 버린다
  - 부족하면 실패
- 보급:
  - 보급 시 `2`를 내고 교환 가능

### 건강 검진
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `state.global_rent_half_this_turn = True`
  - 이번 라운드 렌트 계산에 전역 절반 적용

### 극심한 분리불안
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 다른 살아 있는 플레이어 중 가장 먼 위치를 찾아
  - 그 위치로 즉시 도착 처리
  - 반환 타입: `ARRIVAL_THEN_MOVE`

### 신의뜻
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_same_tile_shard_rake_this_turn = True`
- 실제 발동:
  - 같은 칸에 다른 플레이어와 함께 도착했을 때만 후속 처리

### 도움 닫기
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_encounter_boost_this_turn = True`
- 실제 발동:
  - 그 턴 이동 중 중간 경로에서 다른 플레이어 말을 처음 만났을 때
  - 추가 `2d6`

### 우대권
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.rent_waiver_count_this_turn += 1`
  - 다음 렌트 1회를 `0`으로 만든다

### 무료 증정
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_free_purchase_this_turn = True`
  - 다음 구매 시도 1회를 무료화
- 주의:
  - 성공 여부와 무관하게 구매 시도에 들어가면 소모된다

### 가벼운 분리불안
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_same_tile_cash2_this_turn = True`
- 실제 발동:
  - 같은 칸 도착 시 같은 칸의 다른 플레이어 수만큼 `2` 현금씩 획득

### 마당발
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_one_extra_adjacent_buy_this_turn = True`
- 실제 발동:
  - 다음 유효 도착 이벤트에서 인접 같은 블록 토지 1개 추가 매수 시도

### 강제 매각
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 아니오
- 현재 처리:
  - 손패에 들고 있는 상태에서 적 소유 타일 도착 시 자동 확인
  - `_apply_force_sale(...)` 실행
- 실제 동작:
  - 카드를 소비
  - 해당 타일을 은행에 강제 매각
  - 원래 소유자에게 구매 비용 환급 및 타일 코인 반환 규칙을 적용
- 주의:
  - 일반 잔꾀 단계에서 직접 고르는 카드가 아니다

### 호객꾼
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_obstacle_this_round = True`
  - 다른 플레이어가 이동 시, 호객꾼 소유자 말이 있는 칸 경유에 추가 이동 비용(감속) 적용
  - 이동 로그에 `obstacle_slowdown`이 기록됨

### 뇌고왕
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.trick_personal_rent_half_this_turn = True`
- 실제 발동:
  - 렌트 계산에서 payer/owner 절반 보정으로 사용

### 재뿌리기
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 상대 타일 중 엔진이 `highest=True` 기준으로 1개 자동 선택
  - `state.tile_rent_modifiers_this_turn[pos] = 0`
- 의미:
  - 그 타일의 이번 라운드 렌트를 0으로 만든다

### 긴장감 조성
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 자기 타일 중 엔진이 `highest=True` 기준으로 1개 자동 선택
  - `state.tile_rent_modifiers_this_turn[pos] = max(2, 기존값 * 2)`
- 의미:
  - 그 타일의 이번 라운드 렌트를 최소 2배로 만든다

### 느슨함 혐오자
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `state.global_rent_double_this_turn = True`

### 극도의 느슨함 혐오자
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `state.global_rent_double_permanent = True`

### 무역의 선물
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 내 타일 중 `highest=False` 기준 1개 자동 선택
  - 상대 타일 중 `highest=True` 기준 1개 자동 선택
  - 두 타일 소유권을 교환
- 주의:
  - 현재 구현은 완전 자동 선택이다
  - 인간 플레이 UI에서는 별도 타일 선택 메뉴가 필요하다

### 뭘리권
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 아니오
- 현재 처리:
  - 이동 굴림 직후 `_try_anytime_rerolls(...)`에서만 자동 검사
  - landing score가 좋아질 때 1회 재굴림에 사용
- 주의:
  - 일반 잔꾀 단계에서 직접 고르는 카드가 아니다

### 뭔칙휜
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 아니오
- 현재 처리:
  - `_try_anytime_rerolls(...)`에서 자동 검사
  - 최대 2번 취소 예산을 가진 강화형 재굴림

### 과속
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 현금 `2`가 있어야 사용 가능
  - 사용 시 `cash -= 2`
  - `player.trick_dice_delta_this_turn += 1`

### 저속
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `cash += 2`
  - `player.trick_dice_delta_this_turn -= 1`

### 뇌절왕
- 매수: 1
- `is_anytime`: 예
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리 1:
  - 직접 사용하면 `player.trick_zone_chain_this_turn = True`
- 현재 처리 2:
  - 실제 연쇄 이동 활성 코드는 `손패에 "뇌절왕"이 남아 있는지`를 확인한다
  - 자기 블록의 `T2`, `T3`, `MALICIOUS`에 도착하면 카드를 소비하고 추가 주사위 이동
- 중요:
  - 현재 구현은 `플래그 기반 설명`과 `실제 활성 로직`이 어긋난다
  - 즉 턴 잔꾀 단계에서 먼저 써버리면, 이후 도착 시 연쇄 이동이 안 붙을 가능성이 높다

### 이럇!
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - 살아 있는 모든 플레이어의 `trick_dice_delta_this_turn += 1`

### 번뜩임
- 매수: 1
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `_apply_flash_trade(...)` 호출
  - 살아 있는 상대 중 잔꾀가 있는 플레이어만 대상
  - 내 카드 1장과 상대 카드 1장을 교환
- 현재 선택 방식:
  - 내 카드는 `min(player.trick_hand, key=my_value)`로 자동 선택
  - 상대 카드는 공개 카드 우선에서 `max(..., key=their_value)`로 자동 선택
- 중요:
  - 현재 구현은 `1장 교환`이다
  - 설명문상 여러 장 교환처럼 읽혀도, 현재 소스는 그렇지 않다

### 아주 큰 화목 난로
- 매수: 2
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.shards += 1`
  - `F +1`

### 거대한 산불
- 매수: 2
- `is_anytime`: 아니오
- 자신의 턴 잔꾀 단계 선택 가능: 예
- 현재 처리:
  - `player.shards += 2`
  - `F +2`

## 6. 현재 구현상 중요한 불일치 / 주의점

### 성물 수집가
- 버프 값은 쌓이지만 현재 활성 소비처가 보이지 않는다.

### 뇌절왕
- 직접 사용 시 세우는 플래그와 실제 연쇄 이동 발동 경로가 다르다.
- 현재 구현 기준으로는 `손패에 들고 있다가 도착 시 소비`가 실제 동작 경로다.

### 번뜩임
- 현재 구현은 `1대1 교환`이다.

### 호객꾼
- 미구현 상태가 아니며, 현재는 라운드 단위 장애물 감속 플래그로 동작한다.

## 7. 인간 플레이 / 시각화에서 필요한 추가 UI

현재 구현 기준으로 실제 플레이 UI가 필요해지는 항목:

- 무역의 선물
  - 내 타일 선택
  - 상대 타일 선택
- 재뿌리기
  - 대상 타일 선택
- 긴장감 조성
  - 대상 타일 선택
- 번뜩임
  - 대상 플레이어 선택
  - 보낼 카드 선택
  - 받을 카드 선택
- 강제 매각
  - 현재 구현은 자동 트리거지만, 인간 플레이용으론 발동 확인 UI가 필요할 수 있다
- 뭘리권 / 뭔칙휜
  - 현재는 자동 판단이지만, 인간 플레이용으론 재굴림 여부 prompt가 필요하다

## 8. 문서 사용 규칙

이 문서는 현재 소스의 실제 처리만 설명한다.

다음과 같은 질문의 기준 문서로 사용하면 된다.
- 지금 이 카드가 실제로 자동 선택인지 수동 선택인지
- 언제나 잔꾀인지
- 자신의 턴 잔꾀 단계에서 직접 고를 수 있는지
- 어떤 상태 변수에 기록되는지
- 실제로 어디서 소비되는지

반대로 다음은 이 문서만으로 확정하면 안 된다.
- 카드 설명문이 의도한 원래 규칙
- 향후 시각화/인간 플레이에서 어떤 UI를 채택할지
- 미구현 카드의 최종 의도
