# [NOTE] Runtime Unstable Points (2026-03-31)

이 문서는 현재 커밋 시점에서 "재현 가능성이 있거나 운영 중 혼동을 줄 수 있는" 불안정/주의 지점을 기록한다.

## 1) 관찰된 증상

- 사람+AI 혼합 세션에서 화면이 초기 상태에 머무르며 `runtime: recovery_required`가 유지되는 사례가 있었다.
- 동일 코드라도 실행 중인 서버 프로세스가 과거 버전이면, UI에서 같은 증상이 반복되어 보일 수 있었다.

## 2) 현재 코드 기준 완화 상태

- `POST /sessions/{id}/start` 시 runtime 시작 경로를 표준화했다.
- WS seat 연결 시 `recovery_required` 상태에 대한 복구 시작 경로를 유지했다.
- session `join` 단계에서 연결 상태를 즉시 true로 올리지 않고, 실제 WS connect/disconnect로 반영되게 정리했다.

## 3) 아직 운영상 주의가 필요한 부분

- 서버 핫 리로드/다중 프로세스 환경에서 어떤 프로세스가 실제 요청을 처리하는지에 따라 증상이 혼재될 수 있다.
- 클라이언트가 오래 열린 탭/구 버전 번들을 유지하면 체감 증상이 동일하게 보일 수 있다.

## 4) 검증 체크리스트 (수동)

1. FastAPI 서버를 완전히 종료 후 재시작한다.
2. `Lobby -> Create/Join -> Start -> Match` 순서로 진행한다.
3. 서버 로그에서 `session_started`, `runtime_started` 확인.
4. UI에서 `runtime-status`가 `running`으로 전환되는지 확인.
5. `stream` 재연결 후에도 진행 이벤트(seq 증가)가 이어지는지 확인.

## 5) 자동 회귀 테스트 게이트

- 권장 최소 게이트:
  - `python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py -q`
- 전체 서버 게이트:
  - `python -m pytest apps/server/tests -q`

## 6) 후속 개선 후보

- `runtime-status` 상태 전이(`idle -> running -> recovery_required -> running`)를 명시한 상태 머신 테스트 추가.
- 서버 시작 시 orphan/in-progress session 자동 복구 정책을 환경설정으로 세분화.
- 운영 모드에서 연결 타이밍 분석용 구조화 로그 필드 확대(세션ID/좌석/토큰 role/프로세스 식별자).

