# BOARD_LAYOUT_SCHEMA.md

## 목적
외부 보드 스펙 파일(`board_layout.json`, `board_layout.csv`, `board_layout_meta.json`)의 허용 구조를 명시한다.

## 1. JSON 단일 파일 형식
파일 하나에 보드 레벨 메타와 타일 리스트를 함께 넣는다.

### top-level 필드
- `layout_metadata` : 보드 규칙 메타데이터 객체
- `tiles` : 타일 목록 배열

### `layout_metadata` 필드
| 필드 | 설명 |
|---|---|
| `special_tile_s_display_name` | S칸 표시 이름 |
| `f_end_value` | 게임 종료 F 임계값 |
| `f1_increment` | F1 도달/통과 시 F 변화량 |
| `f2_increment` | F2 도달/통과 시 F 변화량 |
| `f1_shards` | F1 보상 조각 수 |
| `f2_shards` | F2 보상 조각 수 |
| `malicious_land_multiplier` | 악성 토지 비용 배수 |
| `s_cash_plus1_probability` | S칸 +1냥 확률 |
| `s_cash_plus2_probability` | S칸 +2냥 확률 |
| `s_cash_minus1_probability` | S칸 -1냥 확률 |
| `zone_colors` | 구역 색상 순서 배열 |

### `tiles` 원소 필드
| 필드 | 설명 |
|---|---|
| `index` | 타일 인덱스 |
| `kind` | `F1`, `F2`, `S`, `LAND`, `FORTUNE`, `MALICIOUS` 등 타일 종류 |
| `block_id` | 일반 토지 구역 묶음 id |
| `zone_color` | 색상 속성 |
| `purchase_cost` | 구매가 |
| `rent_cost` | 통행료 |

## 2. CSV + sidecar meta 형식
CSV는 타일 목록만 가지고, `board_layout_meta.json`이 보드 레벨 메타를 가진다.

### CSV 헤더
`index,kind,block_id,zone_color,purchase_cost,rent_cost`

### sidecar meta JSON
JSON 단일 파일 형식의 `layout_metadata`와 동일 필드를 사용한다.

## 3. 로딩 규칙
- `board_layout_creator.py`가 외부 스펙을 내부 `TileMetadata`/`BoardLayoutMetadata`로 정규화한다.
- 누락 값이 있을 경우 creator의 기본값 또는 `BoardConfig` 기본값이 적용될 수 있다.
- 실험용 보드 스펙을 추가할 때는 가능한 한 이 문서를 먼저 보고 필드를 맞춘다.

## 4. 권장 사항
- `index`는 루프 순서와 일치하게 0 또는 1부터 단조 증가시키는 것을 권장한다.
- `kind`는 엔진이 이해하는 enum/문자열 집합만 사용한다.
- `purchase_cost`, `rent_cost`가 없는 특수칸은 0으로 둔다.
- 새로운 타일 속성 확장이 필요하면 `TileMetadata`, creator, 이 문서를 함께 수정한다.


### 0.7.61 update
Preferred structural form: `economy_profile` instead of embedded `purchase_cost`/`rent_cost`. Embedded numeric costs remain supported only as input aliases.
