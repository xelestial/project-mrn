# EXAMPLE Trick Card Source Snapshot

## 2026-03-28 Audit Warning

This file is still only an example snapshot.

It is **not** valid trick-rule truth for the following reviewed items:
- `성물 수집가`
- `우대권`
- `강제 매각`
- `신의뜻`
- `마당발`
- `뇌절왕`

For those cards, the reviewed rule clarification and change requests live in:
- [GPT_TRICK_CARD_RUNTIME_GUIDE.md](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md)

If this example snapshot and the guide disagree:
- trust the guide's `2026-03-28 Manual Audit Corrections`
- treat this file as an implementation-shape example only

이 파일은 **유효한 잔꾀 규칙 문서가 아니다**.

목적:
- 현재 소스코드가 잔꾀를 어떤 범주로 보고 있는지 예시를 빠르게 보여주기
- 구조 검토용 샘플 제공

이 파일을 authoritative source로 쓰면 안 되는 이유:
- 카드 설명문 전체 의미를 다 담지 않는다
- 상태 플래그가 실제 어디서 소비되는지 충분히 설명하지 않는다
- 자동 선택 / 수동 선택 / held 트리거 / 재굴림 훅 차이를 완전히 설명하지 않는다
- 실제 검증 기준 문서는
  - [C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md)
  - [C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py)
  - [C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\effect_handlers.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\effect_handlers.py)
  를 함께 봐야 한다

## 예시 분류

### 직접 사용 즉시 상태를 바꾸는 카드
- `성물 수집가` -> `extra_shard_gain_this_turn += 1`
- `건강 검진` -> `global_rent_half_this_turn = True`
- `우대권` -> `rent_waiver_count_this_turn += 1`
- `뇌고왕` -> `trick_personal_rent_half_this_turn = True`
- `무료 증정` -> `trick_free_purchase_this_turn = True`
- `신의뜻` -> `trick_same_tile_shard_rake_this_turn = True`
- `가벼운 분리불안` -> `trick_same_tile_cash2_this_turn = True`
- `마당발` -> `trick_one_extra_adjacent_buy_this_turn = True`
- `도움 닫기` -> `trick_encounter_boost_this_turn = True`
- `느슨함 혐오자` -> `global_rent_double_this_turn = True`
- `극도의 느슨함 혐오자` -> `global_rent_double_permanent = True`
- `과속` -> `cash -2`, `trick_dice_delta_this_turn += 1`
- `저속` -> `cash +2`, `trick_dice_delta_this_turn -= 1`
- `이럇!` -> alive 전원 `trick_dice_delta_this_turn += 1`

### 자동 대상 선택 카드
- `재뿌리기` -> 상대 타일 중 엔진 자동 선택, 이번 라운드 렌트 `0`
- `긴장감 조성` -> 자기 타일 중 엔진 자동 선택, 이번 라운드 렌트 `2배 이상`
- `무역의 선물` -> 내 저가치 타일 + 상대 고가치 타일 자동 교환
- `번뜩임` -> 자동 `1장 대 1장` 교환

### 손패에 들고 있다가 다른 훅에서 처리되는 카드
- `강제 매각` -> 적 소유 타일 도착 시 자동 발동
- `뭘리권` -> 이동 굴림 후 재굴림 훅
- `뭔칙휜` -> 이동 굴림 후 재굴림 훅
- `뇌절왕` -> 현재 구현상 실제 연쇄 이동은 도착 처리에서 손패 보유 여부로 판단

### burden 카드
- `무거운 짐` -> 사용 시 `4` 지불 후 버림
- `가벼운 짐` -> 사용 시 `2` 지불 후 버림

### 현재 구현상 주의가 필요한 카드
- `성물 수집가` -> 값은 쌓이지만 활성 소비처가 보이지 않음
- `호객꾼` -> 분류는 있으나 활성 처리 경로가 불명확함
- `뇌절왕` -> 설명 플래그와 실제 활성 코드가 어긋남
- `번뜩임` -> 설명보다 좁게 구현되어 현재는 1대1 교환만 함

## 다시 강조

이 파일은 **예시 스냅샷**이다.

실제 잔꾀 처리의 정확한 기준은 아래 문서다.
- [C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md)
