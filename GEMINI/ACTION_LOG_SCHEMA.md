# ACTION_LOG_SCHEMA.md

## 목적
`action_log`의 공통 구조와 주요 row 타입을 명시한다. 이 문서는 사람이 로그를 해석할 때 기준이 되고, 로그 파서/검증 테스트의 계약 문서 역할도 한다.

## 공통 필드
대부분의 row는 아래 필드를 공통으로 가진다.

| 필드 | 설명 |
|---|---|
| `seq` | 게임 내 단조 증가 로그 순서 번호 |
| `version` | 엔진 버전 문자열 |
| `event` | 이벤트 이름 |
| `event_kind` | 로그 행 분류 (`semantic_event`, `runtime_event`, `summary_event` 등) |
| `component` | 이벤트를 발생시킨 주체 (`engine`, `event_bus`, `policy`, `parser` 등) |
| `round_index` | 가능한 경우 현재 라운드 |
| `turn_index` | 가능한 경우 현재 턴 인덱스 |
| `player` | 가능한 경우 플레이어 id |
| `character` | 가능한 경우 현재 인물 |

## semantic event row
semantic event row는 이벤트 버스에서 발생한 의미 단위 이벤트를 나타낸다.

추가 필드:
- `dispatch_mode`
- `handler_count`
- `returned_non_none`
- `args`
- `kwargs`
- `results`

대표 예:
- `tile.purchase.attempt`
- `rent.payment.resolve`
- `fortune.card.apply`
- `landing.force_sale.resolve`
- `lap.reward.resolve`
- `game.end.evaluate`

## runtime event row
runtime event row는 엔진 실행 중 상태 전환/편의 로그를 남긴다.

대표 예:
- `turn_start`
- `turn`
- `weather_round`
- `game_end`
- `trick_used`

## parsed turn bundle
`action_log_parser.py`는 raw row를 turn 단위로 묶어서 parsed log를 만든다. parsed turn bundle의 핵심 필드는 다음과 같다.

- `round_index`
- `turn_index`
- `player`
- `character`
- `move_roll`
- `landing_type`
- `semantic_events`
- `runtime_events`
- `resource_deltas`
- `human_summary`

## 설계 원칙
- semantic event는 가능한 한 효과 단위를 직접 표현한다.
- runtime event는 사람이 실행 흐름을 읽기 쉽게 보조한다.
- summary용 파생 정보는 raw log를 파괴하지 않고 parser에서 재구성한다.
- 내부 객체는 로그에 그대로 덤프하지 않고 요약된 dict/string으로 직렬화한다.

## 주의 사항
- semantic event가 없더라도 runtime event만 있는 턴이 있을 수 있다. 가능하면 `turn.noop` 같은 표준 semantic row로 정규화하는 방향을 우선 고려한다.
- 로그 스키마를 바꾸면 `test_event_effects.py`, parser 검증 코드, 이 문서를 함께 갱신한다.
