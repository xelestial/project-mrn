# METADATA_REGISTRY.md

## 목적
이 문서는 프로젝트에서 사용되는 메타데이터의 종류, 소유 위치, 갱신 주체, 주 사용처를 한 곳에서 찾기 위한 레지스트리다.

## 사용 원칙
- 새 메타데이터 구조를 추가하면 이 문서에도 항목을 추가한다.
- 메타데이터 구조가 바뀌면 `CHANGELOG.md`와 대응 문서도 같이 갱신한다.
- 정적 메타데이터와 런타임 상태 메타데이터를 혼동하지 않는다.

## 분류

### 1. 프로젝트 메타데이터
| 이름 | 위치 | 소유/갱신 | 설명 | 주요 사용처 |
|---|---|---|---|---|
| 버전 문자열 | `VERSION.txt`, `metadata.py` | 릴리스/패치 시 수동 갱신 | 현재 패키지 버전 | summary, 로그, 테스트, 보고서 |
| 릴리스 날짜 | `metadata.py` | 릴리스 시 수동 갱신 | 현재 버전 날짜 | 보고서/summary |
| 릴리스 노트 | `metadata.py`, `CHANGELOG.md` | 릴리스 시 수동 갱신 | 이번 버전 핵심 변경 | 결과 파일, 개발 기록 |

### 2. 보드 정적 메타데이터
| 이름 | 위치 | 설명 | 주요 사용처 |
|---|---|---|---|
| `TileMetadata` | `config.py` | 타일 index, kind, block_id, zone_color, purchase_cost, rent_cost | 보드 생성, 테스트, 외부 보드 스펙 정규화 |
| `BoardLayoutMetadata` | `config.py` | F/S/악성 토지/색상/종료값 등 보드 레벨 규칙 | 보드 규칙 수치 설정 |
| 외부 보드 스펙 | `board_layout.json`, `board_layout.csv`, `board_layout_meta.json` | JSON/CSV 기반 보드 정의 | `board_layout_creator.py` |

### 3. 런타임 상태 메타데이터
| 이름 | 위치 | 설명 | 주요 사용처 |
|---|---|---|---|
| `TileState` | `state.py` | 정적 타일 메타 + owner_id + score_coins | 엔진, AI, 로그 |
| `PlayerState` | `state.py` | 플레이어 자원/포지션/인물/상태 | 엔진, AI, 결과 집계 |
| `GameState` | `state.py` | 현재 게임 전체 상태의 집합 | 엔진, 핸들러, 룰 스크립트 |

### 4. 이벤트 메타데이터
| 이름 | 위치 | 설명 | 주요 사용처 |
|---|---|---|---|
| semantic event 이름 | `engine.py`, `effect_handlers.py`, `event_system.py` | 예: `tile.purchase.attempt`, `game.end.evaluate` | 이벤트 분리, override, 로그 추적 |
| dispatch 메타 | `event_system.py` | dispatch mode, handler_count, returned_non_none | semantic trace log |

### 5. 로그 메타데이터
| 이름 | 위치 | 설명 | 주요 사용처 |
|---|---|---|---|
| structured action log row | `engine.py`, `event_system.py` | `seq`, `event_kind`, `component`, `round_index`, `turn_index`, `player` 등 | 디버깅, 파싱, 사후 분석 |
| parsed turn log | `action_log_parser.py` | raw log를 turn bundle로 재구성한 결과 | 사람/기계 읽기 쉬운 후처리 |

### 6. 문서/검증 메타데이터
| 이름 | 위치 | 설명 | 주요 사용처 |
|---|---|---|---|
| source-doc pair | `doc_integrity.py` | 어떤 `.py`와 어떤 `.md`가 대응하는지 | 문서 무결성 검사 |
| read order | `MODULE_READ_ORDER.md` | 어떤 문서부터 읽을지 | 프로젝트 복구/온보딩 |
| change workflow | `CHANGE_WORKFLOW_GUIDE.md` | 수정 절차와 기록 규칙 | 개발 절차 |

## 갱신 체크리스트
- 새 메타데이터 타입이 생겼는가?
- 저장 위치가 바뀌었는가?
- 갱신 주체/타이밍이 바뀌었는가?
- summary/log/parser/tests 중 영향받는 곳이 있는가?
- 이 문서와 `CHANGELOG.md`를 같이 갱신했는가?
