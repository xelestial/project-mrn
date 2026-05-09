# Redis State Inspector

## Goal

Redis만 보고도 현재 세션의 권위 상태, 프롬프트 대기 상태, viewer별 view_commit/outbox 전달 상태를 한 번에 이해하고, 흔한 불일치를 기계적으로 검출한다.

이 작업은 런타임 동작을 바꾸지 않는다. 기존 Redis 저장 구조 위에 읽기 전용 진단 서비스를 추가한다.

## Current Problems

1. Redis debug snapshot은 정보 묶음이지 판정기가 아니다.
   - 원인: checkpoint/current_state/view_commit/prompt/outbox가 각각 저장되지만, 서로 같은 상태를 가리키는지 검증하는 계층이 없다.
   - 해결: RedisStateInspector가 모든 관련 저장소를 읽고 `issues[]`로 불변식 위반을 명시한다.

2. prompt가 남았을 때 정상 대기인지 orphan인지 빠르게 구분하기 어렵다.
   - 원인: active prompt, pending hash, lifecycle hash, runtime status가 분산되어 있다.
   - 해결: active request id와 pending/lifecycle/resolved 기록을 비교한다.

3. view_commit이 복원 기준인데 viewer별 commit freshness를 바로 알기 어렵다.
   - 원인: view_commit_index에는 viewer label이 있지만 최신 commit_seq와 각 viewer payload를 같이 검증하지 않는다.
   - 해결: index latest commit과 각 viewer payload commit을 비교한다.

4. WebSocket outbox 검증이 사후 분석에 약하다.
   - 원인: viewer outbox는 기록되지만 현재 세션 리포트와 연결되지 않는다.
   - 해결: 최신 outbox 레코드와 viewer scope/message type/commit_seq를 요약한다.

## Target Shape

`RedisStateInspector.inspect_session(session_id)`는 JSON 직렬화 가능한 dict를 반환한다.

주요 섹션:

- `summary`: 사람이 바로 읽는 세션 상태
- `state`: checkpoint/current_state/view_commit/runtime lease/status의 compact view
- `prompts`: pending/resolved/lifecycle active prompt 요약
- `view_commits`: viewer별 commit seq와 runtime pointer
- `outbox`: viewer outbox 최신 전달 기록
- `issues`: severity/code/message/evidence 구조의 진단 결과
- `recommendations`: issue code 기반 다음 조치
- `raw_keys`: 조사해야 할 Redis key 이름

진단 상태:

- `ok`: issue 없음
- `warning`: warning만 있음
- `critical`: critical issue 있음

## Invariants

1. checkpoint가 없으면 세션 상태를 Redis만으로 설명할 수 없다.
2. checkpoint의 `latest_commit_seq`와 view_commit_index의 `latest_commit_seq`가 다르면 복원 기준이 흔들린다.
3. view_commit_index에 등록된 viewer payload는 최신 commit_seq를 따라와야 한다.
4. runtime이 `failed`면 critical이며 exception/error/traceback을 evidence에 포함한다.
5. runtime/checkpoint가 active prompt를 가리키는데 pending prompt가 없으면 waiting 상태에서는 critical이다.
6. pending prompt가 있는데 runtime/checkpoint/view_commit active prompt 어디에도 연결되지 않으면 warning이다.
7. running 계열 runtime이 lease 없이 떠 있으면 warning이다.
8. viewer outbox는 TTL이 있는 사후 분석 자료이므로 없다는 사실만으로 critical이 아니다.

## Implementation Steps

1. RED test 작성
   - 정상 세션: checkpoint, runtime status, lease, pending prompt, viewer별 view_commit, outbox가 일치하면 critical issue가 없다.
   - 불일치 세션: failed runtime, commit seq mismatch, missing pending prompt가 issue로 검출된다.

2. 읽기 전용 서비스 추가
   - `apps/server/src/services/redis_state_inspector.py`
   - 기존 `RedisGameStateStore`, `RedisRuntimeStateStore`, `RedisPromptStore`, `RedisStreamStore`를 조합한다.
   - private key 삭제나 TTL 변경은 하지 않는다.

3. CLI 추가
   - `tools/checks/redis_state_inspector.py`
   - JSON 출력, pretty 옵션, critical/warning exit gate를 제공한다.

4. 검증
   - 신규 unit test 통과
   - 기존 Redis realtime test 일부 통과
   - CLI가 fake가 아닌 로컬 Redis URL 설정을 받을 수 있는지 import/argparse 수준 검증

## Residual Risks

1. Redis에 남지 않는 오래된 이벤트까지 완전 복구할 수는 없다.
   - 대응: outbox/event debug TTL은 분석용 보조 자료로 명시하고 authoritative 기준은 view_commit/current_state/checkpoint로 둔다.

2. current_state schema가 계속 진화한다.
   - 대응: inspector는 schema-specific deep parse 대신 compact extraction과 cross-store invariant 위주로 유지한다.

3. 너무 많은 raw payload를 출력하면 분석 컨텍스트를 잡아먹는다.
   - 대응: 기본 출력은 compact summary이고, raw key 이름만 제공한다. 필요하면 Redis에서 직접 특정 key를 조회한다.

## Completion Criteria

- Redis inspector unit tests are green.
- CLI can print a compact diagnostic JSON for a session id.
- The report contains enough information to answer:
  - 현재 게임은 어느 라운드/턴/플레이어/프롬프트에 있는가?
  - 최신 view_commit은 누구에게 어느 seq까지 만들어졌는가?
  - active prompt와 pending/lifecycle 상태가 일치하는가?
  - runtime failed, stale commit, orphan prompt 같은 문제가 있는가?
