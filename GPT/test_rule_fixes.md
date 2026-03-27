# test_rule_fixes.py

룰 수정 회귀 테스트 문서.

## 이번 갱신
- 보드 구조 변경에도 깨지지 않도록 테스트 좌표를 메타데이터 기반으로 찾는다.
- `block_tile_positions`, `tile_positions`, `first_tile_position` 같은 helpers를 사용해
  - 3칸짜리 block
  - 첫 번째 토지
  - 첫 번째 T3
  - 위험 토지 집합
  을 동적으로 찾는다.

## 의도
맵을 3-2-3, 2-3-2, 또는 다른 side pattern으로 바꿔도 테스트가 의미를 유지하게 한다.


## 0.7.57
Rule tests cover purchase-time token placement max 1, takeover coin transfer, and force-sale coin return.

## 0.7.61
- 범용 생존 점수가 인물/잔꾀/주사위 카드/랩 보상 선택에 공통 반영되는지 회귀 테스트를 추가했다.
- 저현금 위기에서 성장형 인물 대신 탈출/저비용 기능형을 고르고, 랩 보상은 cash로 후퇴하며, 방어성 잔꾀와 탈출 동선을 더 선호하는지 확인한다.

- Added regression coverage for **non-leader F suppression** and **leader-only F acceleration**.
- Added regression coverage for non-leader `choose_geo_bonus()` preferring `cash` over shard/coin tempo when F acceleration is strategically bad.


## v7.61 forensic patch notes
- Added regression coverage for F clamp logging and chunk-merge forensic metadata repair.

- 교리 연구관/감독관의 턴 시작 짐 제거(자기 짐 / 같은 team_id 팀원 짐) 회귀 테스트 추가.

- 최신 변경: `중매꾼`은 인접 추가 매입 시에만 조각 1개가 필요하다. `건설업자`는 기본 착지 매입에서 조각 1개를 내면 무료 건설을 하며, 조각이 없으면 일반 비용을 낸다.

- 2026-03-26: cleanup risk tests now cover next-draw vs full-cycle probability tracking and end-turn probabilistic cleanup pressure.

- 탐관오리 회귀 테스트는 공납 기준을 탐관오리 자신의 조각으로 검증한다.
- 어사/탐관오리는 같은 카드이므로 동시 존재 가정 테스트를 두지 않는다.

- 탐관오리 공납 회귀 테스트는 탐관오리 자신의 조각 5개일 때 2냥 공납과 추가 주사위를 확인한다.
