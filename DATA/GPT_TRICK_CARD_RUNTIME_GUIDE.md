# GPT Trick Card Runtime Guide

이 문서는 `GPT/` 현재 소스코드 기준으로 잔꾀가 실제로 어떻게 처리되는지 정리한 문서입니다.

중요:
- 이 문서는 카드 설명 요약이 아니라 `현재 구현` 설명입니다.
- 규칙 텍스트와 소스 구현이 다르면, 이 문서는 소스 구현을 우선해서 적습니다.

기준 소스:
- [trick.csv](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\trick.csv)
- [trick_cards.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\trick_cards.py)
- [state.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\state.py)
- [engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py)
- [effect_handlers.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\effect_handlers.py)

## 1. 기본 구조

현재 구조는 이렇게 되어 있습니다.

1. [trick.csv](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\trick.csv)에서 카드 정의를 읽습니다.
2. [trick_cards.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\trick_cards.py)가 `TrickCardDef`, `TrickCard`를 만듭니다.
3. [state.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\state.py)의 `PlayerState.trick_hand`가 실제 손패를 가집니다.
4. [engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py)가
   - 잔꾀 사용 단계
   - 공개/비공개 상태
   - 보급 시 burden 교환
   - 도착/이동 중 후속 사용
   를 관리합니다.
5. [effect_handlers.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\effect_handlers.py)의 `handle_trick_card(...)`가 카드별 실제 효과를 적용합니다.

## 2. 덱과 카드 정의

현재 덱 정의는 `trick.csv` 기준입니다.

- 카드 종류 수: `28`
- 실카드는 `전체 장수`만큼 복제됩니다.
- 각 실카드는 `deck_index`를 갖습니다.

`TrickCard`의 현재 핵심 속성:
- `name`
- `description`
- `deck_index`

추가 판정:
- `is_burden`
  - `무거운 짐`, `가벼운 짐`만 burden으로 취급
- `burden_cost`
  - `무거운 짐 = 4`
  - `가벼운 짐 = 2`
- `is_anytime`
  - 현재는 설명 문자열에 `언제나 사용할 수 있습니다`가 포함되는지로 판정

즉 `언제나`는 별도 메타가 아니라 설명 문자열 기반입니다.

## 3. 공개 / 비공개 처리

[state.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\state.py) 기준:

- 플레이어는 `trick_hand` 전체를 보유
- 그중 `hidden_trick_deck_index` 1장만 비공개
- `public_trick_cards()`는 숨긴 1장을 제외한 카드 반환
- `hidden_trick_count()`는 손패가 있으면 `1`, 없으면 `0`

즉 현재 공개 규칙은 단순합니다.
- 손패 0장: 숨김 0장
- 손패 1장 이상: 숨김 1장, 나머지 공개

## 4. 턴 중 잔꾀 사용 단계

[engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py) 기준:

### 4.1 언제나 잔꾀
- 자신의 턴 잔꾀 단계에서 먼저 처리
- 반복적으로 여러 장 사용할 수 있음

### 4.2 일반 잔꾀
- 그다음 일반 잔꾀 처리
- 일반 잔꾀는 현재 기본적으로 `1장만` 사용

### 4.3 일반 잔꾀 단계에서 바로 쓰지 않는 카드
현재 `engine._is_trick_phase_usable(...)` 기준으로 아래 카드는 일반 잔꾀 단계에서 즉시 사용하지 않습니다.

- `강제 매각`
- `뭘리권`
- `뭔칙휜`
- `호객꾼`

즉 이 카드들은 손패에 들고 있다가 다른 시점 로직에서 처리됩니다.

## 5. 보급과 burden 교환

[engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py) 기준:

- `F`가 보급 임계치를 넘으면 `trick_supply` 발생
- burden 카드가 있으면 `choose_burden_exchange_on_supply(...)`로 교환 여부 판단
- 비용을 내고 burden 제거 후 새 잔꾀 1장 획득
- 이후 손패가 5장이 되도록 보충

즉 burden은:
- 사용해서 버릴 수 있고
- 보급 때 비용 내고 교환할 수도 있습니다.

## 6. 카드별 현재 처리

아래는 `현재 소스코드가 실제로 하는 처리`입니다.

### 6.1 즉시 효과 / 상태 플래그형

- `성물 수집가`
  - `extra_shard_gain_this_turn += 1`
- `건강 검진`
  - 이번 턴 전역 통행료 절반
- `우대권`
  - 이번 턴 통행료 1회 면제
- `뇌고왕`
  - 이번 턴 본인 통행료 절반
- `뇌절왕`
  - 자기 구역 연쇄 이동용 `trick_zone_chain_this_turn = True`
- `무료 증정`
  - 이번 턴 무료 구매 1회
- `신의뜻`
  - 같은 칸 조우 시 shard 기반 현금 효과 플래그
- `가벼운 분리불안`
  - 같은 칸 조우 시 cash 효과 플래그
- `마당발`
  - 인접 같은 색 토지 추가 구매 1회 플래그
- `도움 닫기`
  - 이동 도중 조우 시 추가 2d6 이동 플래그
- `느슨함 혐오자`
  - 이번 턴 전역 통행료 2배
- `극도의 느슨함 혐오자`
  - 영구 전역 통행료 2배
- `과속`
  - 현금 `-2`, 주사위 `+1`
- `저속`
  - 현금 `+2`, 주사위 `-1`
- `이럇!`
  - 생존 플레이어 전원 주사위 `+1`
- `아주 큰 화목 난로`
  - shard `+1`, F `+1`
- `거대한 산불`
  - shard `+2`, F `+2`

### 6.2 자동 대상 선택형

이 카드는 인간 플레이 기준으로는 선택 메뉴가 필요하지만, 현재 소스는 자동 선택합니다.

#### `재뿌리기`
- 현재 구현:
  - 상대 타일 하나를 자동 선택
  - 선택 기준: `engine._select_other_player_tile(..., highest=True)`
  - 결과: 그 타일의 이번 턴 통행료를 `0`으로 설정
- 의미:
  - 지금은 사람이 고르는 카드가 아니라 “엔진이 가장 가치 높은 상대 타일을 고르는 카드”입니다.

#### `긴장감 조성`
- 현재 구현:
  - 자기 타일 하나를 자동 선택
  - 선택 기준: `engine._select_owned_tile(..., highest=True)`
  - 결과: 그 타일의 이번 턴 통행료를 `2배 이상`으로 설정
- 의미:
  - 지금은 사람이 고르는 카드가 아니라 “엔진이 가장 가치 높은 자기 타일을 고르는 카드”입니다.

#### `무역의 선물`
- 현재 구현:
  - 내 타일 1개와 상대 타일 1개를 자동 선택
  - 내 타일 기준: `engine._select_owned_tile(..., highest=False)`
  - 상대 타일 기준: `engine._select_other_player_tile(..., highest=True)`
  - 결과: 내 쪽은 낮은 가치 타일, 상대 쪽은 높은 가치 타일을 자동 교환
- 의미:
  - 현재 구현은 완전 자동 교환입니다.
  - 인간 플레이에선 반드시 선택 메뉴가 필요합니다.

#### `번뜩임`
- 현재 구현:
  - 카드 설명처럼 “원하는 장수만큼” 교환하지 않습니다.
  - 현재는 `1장 보내고 1장 받는` 자동 교환입니다.
  - 대상 플레이어도 자동 선택
  - 내가 줄 카드는 burden 쪽을 우선 버리는 방향
  - 받을 카드는 공개된 카드 위주로 가치가 가장 높은 것 선택
- 의미:
  - 현재 구현은 카드 설명과 다를 수 있습니다.
  - 인간 플레이용으로 쓰려면 대상/보낼 카드/받을 카드 선택 UI가 필요합니다.

### 6.3 도착/후속 트리거형

#### `극심한 분리불안`
- 현재 구현:
  - 다른 플레이어 중 가장 먼 위치로 즉시 도착
  - `ARRIVAL_THEN_MOVE` 형태로 처리

#### `강제 매각`
- 현재 구현:
  - 일반 잔꾀 단계에서 바로 처리하지 않음
  - 남의 소유 타일에 도착했을 때 `landing.force_sale.resolve`가 먼저 실행됨
  - 카드 소비 후 타일을 은행으로 강제 매각
  - 원 소유자는 구매비 환급/배치 승점 코인 반환 등을 받음
- 의미:
  - 도착 시점 트리거형 카드입니다.

#### `뭘리권`, `뭔칙휜`
- 현재 구현:
  - 일반 잔꾀 단계에서 바로 처리하지 않음
  - 이동 계산 중 `_try_anytime_rerolls(...)`에서 자동으로 사용할 수 있음
  - 현재 정책은 재굴림 전후 landing score를 비교해서 자동 소비
  - `뭘리권`은 1회, `뭔칙휜`은 최대 2회 budget 성격

#### `호객꾼`
- 현재 구현:
  - 일반 잔꾀 단계에선 보류형
  - 하지만 현재 코드상 별도 해상도/소비 경로가 명확하게 이어지지 않음
- 의미:
  - held 성격으로 분류돼 있으나, 현재 구현은 부분적 또는 미완성으로 보는 것이 안전합니다.

### 6.4 burden

#### `무거운 짐`
- 현재 구현:
  - 사용 시 `4냥` 지불 후 제거
  - 보급 시에도 교환 가능

#### `가벼운 짐`
- 현재 구현:
  - 사용 시 `2냥` 지불 후 제거
  - 보급 시에도 교환 가능

## 7. 상태 플래그 목록

아래 플래그가 현재 잔꾀 후속 해석에 사용됩니다.

- `trick_free_purchase_this_turn`
- `trick_dice_delta_this_turn`
- `trick_personal_rent_half_this_turn`
- `trick_same_tile_cash2_this_turn`
- `trick_same_tile_shard_rake_this_turn`
- `trick_one_extra_adjacent_buy_this_turn`
- `trick_encounter_boost_this_turn`
- `trick_force_sale_landing_this_turn`
- `trick_zone_chain_this_turn`

즉 잔꾀는 “즉시 효과”만 있는 게 아니라, 턴 중 다른 시스템이 읽는 상태를 많이 바꿉니다.

## 8. 현재 구현 기준의 불명확/주의 지점

- `번뜩임`
  - 설명은 장수 선택형으로 읽히지만 현재 구현은 `1장 교환`
- `호객꾼`
  - held 분류는 되어 있지만 현재 코드상 별도 활성 처리 경로가 약함
- `언제나`
  - 현재는 설명 문자열 기반 판정
  - 장기적으로는 구조화된 메타가 필요

## 9. 인간 플레이 / 시각화에서 필요한 선택 UI

현재 구현 기준으로, 인간 플레이로 가면 아래는 별도 메뉴 또는 즉시 prompt가 필요합니다.

- `무역의 선물`
  - 내 타일 선택
  - 상대 타일 선택
- `재뿌리기`
  - 대상 타일 선택
- `긴장감 조성`
  - 대상 타일 선택
- `번뜩임`
  - 대상 플레이어 선택
  - 내가 줄 카드 선택
  - 내가 받을 카드 선택
- `강제 매각`
  - 도착 시 사용 여부
- `뭘리권`, `뭔칙휜`
  - 이동 중 재굴림 여부

이 때문에 잔꾀를 1차 시각화 범위에서 제외하는 것은 단순 편의가 아니라, 실제로 입력 계약이 아직 복잡하기 때문입니다.
