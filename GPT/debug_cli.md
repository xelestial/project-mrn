# debug_cli.py

엔진 직결형 디버그 CLI. 기존 `GameEngine`과 기존 규칙을 그대로 사용하고, 선택된 좌석만 `HumanPolicy`로 바꿔 끼운다.

핵심 목적:
- 인간 1명 + AI 3명 등 실제 게임 구성 검증
- 모든 숨은 정보 공개(`reveal-all`)
- 액션/이벤트 단위 step review
- 전체 action log 저장

주요 옵션:
- `--humans 1` : 1번 좌석을 인간 플레이어로 지정
- `--ai-mode arena` : 비인간 좌석에 arena 정책 적용
- `--no-step` : 이벤트별 일시정지 없이 연속 실행
- `--show-board-every-step` : 매 step마다 전체 판 출력
- `--show-last-action-json` : 이벤트 JSON 원문도 함께 출력
- `--output-log path.json` : action log 저장

step 모드 명령:
- 엔터: 계속
- `b`: 전체 상태 출력
- `p` 또는 `p2`: 플레이어 상세 출력
- `a`: 마지막 이벤트 JSON 출력
- `q`: 종료

인간 입력 중에도 `:board`, `:pN`, `:last` 명령을 쓸 수 있다.
