# config.py

게임 전역 설정과 보드/경제 규칙 정의 문서.

## 현재 구조
- `BoardConfig`는 side pattern 또는 full loop pattern을 받아 보드 전체를 생성한다.
- 기본 side pattern은 `2-3-2`이며, 한 변의 토지 비용/통행료는 `5,5 - 3,4,3 - 5,5`다.
- `BoardConfig.build_tile_metadata()`는 각 칸의 정적 메타데이터를 만든다.

## TileMetadata
각 타일 메타데이터는 최소한 아래 정보를 가진다.
- `index`: 몇 번째 타일인지
- `kind`: F1/F2/S/T2/T3/MALICIOUS 같은 칸 종류
- `block_id`: 연속 토지 구간 식별자
- `zone_color`: 날씨 색상 구역
- `purchase_cost` / `rent_cost`: 토지 가격 정보

## 설계 의도
- 맵 구조를 바꿔도 타일 정보가 메타데이터에서 일관되게 생성되게 한다.
- 테스트/엔진이 절대 좌표에 의존하지 않도록 보드 질의를 메타데이터 중심으로 옮긴다.
- 공개 메서드는 캐시본의 복사본을 반환해 런타임 변이를 방지한다.


## v0.7.44 board layout separation
- `BoardConfig` now also supports `tile_metadata_layout` as an explicit external board blueprint.
- Use `BoardConfig.from_tile_metadata(...)` to build a metadata-driven board from JSON/CSV creator output.
- Built-in side-pattern generation remains available for default maps, but external layout files are now the preferred path for map variants.


## External board metadata
`BoardLayoutMetadata.from_external_dict(...)` allows board-level rules to be defined in JSON rather than hardcoded defaults. This includes S tile probabilities, F1/F2 shard/F deltas, malicious multiplier, and zone color sequence.


## 0.7.50 update
- `GameConfig` now includes `rule_scripts_path`, allowing external JSON rule-script overrides without editing engine/effect handler code.


## 0.7.57 token rule update
- starting hand score coins remains 2.
- lap rewards are now cash 5 / coins 3 / shards 3.
- can_place_on_first_purchase defaults to true.
- purchase-time placement is capped at 1 coin on the purchased tile.
- revisit placement still allows up to 3, with 3-per-tile cap.


## GameRules sync behavior
`GameConfig.rules` may be omitted, in which case rules are derived from config mirror fields. When explicit rules are injected, config mirror fields are synchronized from those rules for public API stability.


## Rule injection stage 2
`GameConfig` now supports `ruleset_path`. If a ruleset JSON is provided and `rules` is not explicitly injected, the config loads `GameRules` from that file and synchronizes config mirrors.


### 0.7.61 board/rules separation
Board layouts may now describe land tiles with `economy_profile` keys. Numeric costs belong in the ruleset under `economy.land_profiles`.

## Start Resource Defaults
The current default start resource mirror is 20 cash, 0 hand score tokens, and 2 shards. Additional start allocation is rule metadata under `GameRules.start_reward` rather than a config mirror field.

## 2026-05-09 contract sync
Start reward metadata is part of the engine/server parameter contract. Changes to default-visible rule values must update the parameter manifest snapshot and the tests that consume it.
