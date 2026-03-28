# EXAMPLE Trick Card Source Snapshot

이 파일은 **유효한 잔꾀 정보 문서가 아닙니다**.

목적:
- 현재 소스코드가 잔꾀를 어떻게 보고 있는지 예시 형태로 보여주기
- 구조 설계와 검토용 빠른 참고 자료 제공

즉 이 파일은 authoritative rule document가 아니라, 현재 구현 스냅샷 예시입니다.

정식 설명은 아래 문서를 봐야 합니다.
- [GPT_TRICK_CARD_RUNTIME_GUIDE.md](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md)

## 현재 소스 기준 예시 분류

### 즉시 효과 / 상태 플래그
- `성물 수집가` -> extra shard turn buff
- `건강 검진` -> global rent half this turn
- `우대권` -> rent waiver count +1
- `뇌고왕` -> personal rent half this turn
- `뇌절왕` -> zone chain this turn
- `무료 증정` -> free purchase once
- `신의뜻` -> same-tile shard rake flag
- `가벼운 분리불안` -> same-tile cash flag
- `마당발` -> one extra adjacent buy
- `도움 닫기` -> encounter boost flag
- `느슨함 혐오자` -> global rent double this turn
- `극도의 느슨함 혐오자` -> global rent double permanent
- `과속` -> cash -2, dice +1
- `저속` -> cash +2, dice -1
- `이럇!` -> all alive players dice +1
- `아주 큰 화목 난로` -> shards +1, F +1
- `거대한 산불` -> shards +2, F +2

### 자동 대상 선택형
- `재뿌리기` -> highest enemy tile auto-target
- `긴장감 조성` -> highest own tile auto-target
- `무역의 선물` -> lowest own tile + highest enemy tile auto-swap
- `번뜩임` -> auto 1-for-1 trick exchange

### 후속 트리거형
- `극심한 분리불안` -> forced arrival to farthest player
- `강제 매각` -> triggered on landing enemy-owned tile
- `뭘리권` -> reroll helper during movement
- `뭔칙휜` -> reroll helper during movement

### burden
- `무거운 짐` -> pay 4 and discard
- `가벼운 짐` -> pay 2 and discard

### held / incomplete caution
- `호객꾼` -> held-style classification exists, but current active runtime path should be rechecked before treating it as fully supported

## 예시 파일이라서 빠진 것

이 파일에는 아래가 완전하게 들어 있지 않습니다.

- 공개/비공개 처리 세부
- 사용 단계 구분
- 보급 시 교환 처리
- 도착/조우/재굴림 타이밍
- UI에서 필요한 선택 항목
- 규칙 설명과 구현 불일치

따라서 실제 검토 기준은 이 파일이 아니라:
- [GPT_TRICK_CARD_RUNTIME_GUIDE.md](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\DATA\GPT_TRICK_CARD_RUNTIME_GUIDE.md)
- [trick.csv](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\trick.csv)
- [engine.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\engine.py)
- [effect_handlers.py](C:\Users\SIL-EDITOR\Desktop\Workspace\project-mrn\GPT\effect_handlers.py)
를 함께 봐야 합니다.
