# [REVIEW] Pipeline Consistency and Coupling Audit

> Canonical location (migrated on 2026-03-31): `docs/architecture/pipeline-consistency-and-coupling-audit.md`  
> This `PLAN/` file remains as a compatibility mirror for existing links.

Status: `ACTIVE REVIEW`  
Owner: `Shared`  
Updated: `2026-03-31`  
Scope:
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
- `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`

## 목적

현재 문서 집합을 기준으로 다음 4개 파이프라인(설정/기능/점검/확인)을 단일 형태로 명세하고,  
결합도/일관성/테스트 누락/하드코딩 리스크를 점검하여 실행 가능한 보완 항목으로 정리한다.

## 1) 파이프라인 명세 (Canonical)

## A. 설정(파라미터) 파이프라인

`Root Sources -> Registry/Fingerprint -> Resolver -> Runtime Config + Public Manifest -> API/WS Bootstrap -> Frontend Hydration -> Selector/Projection -> UI`

1. Root Sources
- rules/profile source (경제/초기자원/주사위/종료조건)
- board topology source (타일 수/배치/메타)
- content source (인물/잔꾀/운수/날씨의 stable id)
- label source (이벤트/타일/프롬프트 표시 문구)

2. Registry/Fingerprint
- `RootSourceRegistry`가 root source 목록과 fingerprint를 산출
- `manifest_hash`는 resolver 결과 기준 단일 hash로 생성

3. Resolver
- `GameParameterResolver`가 precedence에 따라 `ResolvedGameParameters` 생성
- precedence:
  - engine defaults
  - ruleset profile
  - session overrides
  - runtime-safe validation/clamp

4. Runtime/Manifest Build
- `EngineConfigFactory`가 엔진 실행 config 생성
- `PublicManifestBuilder`가 frontend용 `parameter_manifest` 생성

5. Transport
- REST (`create/get session`) + WS (`session_start`/manifest event)로 manifest 전달

6. Frontend Hydration
- `ParameterManifestStore` 적용
- `manifest_hash` 변화 시 projection/label cache rehydrate

7. UI Projection
- board/seat/labels를 manifest에서만 계산
- default profile(예: 40-tile, 4-seat)은 예시일 뿐 계약 invariant가 아님

## B. 기능(런타임) 파이프라인

`Session Lifecycle -> Runtime Loop -> Event Stream -> Prompt Dispatch -> Decision Ack/Timeout -> Public Snapshot -> Replay`

1. Session lifecycle
- create -> join -> start -> in_progress -> finished

2. Runtime loop
- engine authority 유지
- runtime service는 이벤트를 순서대로 publish

3. Event stream
- monotonic `seq`
- `resume(last_seq)` replay
- heartbeat/backpressure 정보 제공

4. Prompt/Decision
- prompt 생성 (`request_id`)
- human decision 제출
- `decision_ack` (`accepted/rejected/stale`)
- timeout fallback 1회 보장

5. Public snapshot/replay
- stream만으로 현재 공용 상태 복원 가능
- replay export는 contract와 동일 필드 기반

## C. 점검(검증 실행) 파이프라인

`Spec Update -> Contract Test -> Unit Test -> Integration Test -> E2E -> Doc Sync`

1. Spec update
- API/interface/component/decoupling spec 동시 업데이트

2. Contract tests
- event/prompt payload parsing
- missing/partial manifest tolerance

3. Unit tests
- resolver/fingerprint/hash
- selector/projection/label fallback
- prompt lifecycle reducer

4. Integration tests
- reconnect/resume
- stale/timeout decision
- authorization mismatch

5. E2E
- human + AI mixed session
- spectator continuity
- manifest variant scenario (seat/topology/dice 변경)

6. Doc sync
- `PLAN_STATUS_INDEX` 및 상세 spec 동시 반영

## D. 확인(릴리스 게이트) 파이프라인

`Pre-merge Review -> CI Quality Gates -> Manual Scenario Validation -> Release Note`

1. Pre-merge review
- rule-id vs label 분리 여부
- fixed-size literal의 default-profile annotation 여부

2. CI gates
- fingerprint/hash stale-artifact 차단
- contract + integration + e2e green

3. Manual scenarios
- 경제/이동/렌트/운수/날씨/징표 이동의 가시성 확인
- 파산/종료 트리거 및 공용 정보 노출 확인

4. Release note
- payload/label/manifest 변경점 기록

## 2) 감사 결과 (Finding)

| ID | Severity | 분류 | 내용 | 영향 | 조치 |
|---|---|---|---|---|---|
| F-01 | High | 결합도 | 인터페이스 예시에 policy 기본값(`heuristic_v3_gpt`)이 계약값처럼 노출됨 | 런타임 시작 경로가 특정 정책명에 결합될 위험 | interface spec에서 정책값을 optional/주입형으로 변경 |
| F-02 | High | 일관성 | 일부 활성 문서에 `4-seat`, `40-tile` 표현이 DoD/계약처럼 남아 있음 | 비기본 프로파일 대응 시 구현자 오해 가능 | 기본 프로파일 표현으로 강등 + parameterized acceptance 추가 |
| F-03 | Medium | 파이프라인 | 설정 파이프라인 설명이 분산되어 단일 추적 경로가 약함 | 변경 누락 시 계층별 반영 불일치 | 본 문서의 canonical pipeline을 기준으로 문서 간 링크 고정 |
| F-04 | Medium | 테스트 | manifest hash 변경 시 rehydrate 동작의 명시적 테스트 요구가 약함 | 설정 변경 후 UI 불일치 위험 | frontend integration test에 hash-change rehydrate 케이스 명시 |
| F-05 | Medium | 테스트 | partial/unknown manifest/event fallback 테스트 범위가 선언 중심 | 런타임 변형 입력에서 회복탄력성 저하 | contract tests에 unknown kind/partial field fixture 추가 |
| F-06 | Medium | 하드코딩 | 문서 기준으로도 string label과 rule routing이 가까운 구간 존재 | 번역/문구 변경이 규칙 동작에 영향을 줄 가능성 | rule-id 중심 routing + label catalog 분리 원칙 강화 |

## 3) 테스트 누락 보강 항목 (Required Additions)

1. Backend
- root source 변경 -> `source_fingerprints`/`manifest_hash` 자동 변경 테스트
- resolver precedence 충돌 입력 테스트
- partial manifest 생성 거부/보정 정책 테스트

2. Frontend
- `manifest_hash` 변경 시 projection cache reset + rehydrate 테스트
- unknown tile/event/request type fallback selector 테스트
- non-default seat/topology fixture 렌더링 테스트

3. End-to-End
- 기본 프로파일 + 변형 프로파일(좌석/타일/주사위) 연속 재생/라이브 테스트
- reconnect 시 manifest hash 변경 감지 후 정상 복구 테스트

## 4) 하드코딩/고결합 예방 규칙 (Enforced)

1. 계약 문서에서 fixed-size literal을 invariant로 쓰지 않는다.
2. rule routing key는 stable id만 사용한다.
3. display label은 catalog로만 다룬다.
4. frontend projection은 manifest-first다.
5. root source 변경은 resolver/builder 경로 외 수동 반영을 금지한다.

## 5) 이번 업데이트에서 반영된 문서 정합화

- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
  - runtime interface의 정책 기본값 결합 표현 완화
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
  - 고정 좌석/패널 표현을 default-profile 주석 포함 형태로 정리
- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
  - DoD/quality gate의 고정값 표현을 parameterized acceptance로 정리
- `PLAN/PLAN_STATUS_INDEX.md`
  - 본 감사 문서를 active review reference로 추가
- `PLAN/[PLAN]_IMPLEMENTATION_DOCUMENT_USAGE_GUIDE.md`
  - decoupling/contract 작업 시 본 감사 문서 참조 규칙 추가

## 6) 후속 실행 연결

- 실행 기준 계획: `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
- B/F 상세 백로그: `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- 인터페이스/API 계약: `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`, `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`

본 문서는 설계 감사지이며, 구현 완료 기준은 각 `[PLAN]` 문서의 DoD와 테스트 게이트를 따른다.

## 7) Remediation Progress (`2026-03-30`)

| Finding | 상태 | 반영 |
|---|---|---|
| F-01 (runtime policy default coupling) | `DONE` | interface spec/runtime service에서 하드코딩 기본 policy 의존 완화 |
| F-02 (fixed-size wording leakage) | `PARTIAL` | 주요 active 문서를 default-profile 표기로 정리, 일부 historical 문구는 잔존 |
| F-03 (pipeline traceability) | `DONE` | 본 문서의 canonical pipeline + status/usage guide 연결 반영 |
| F-04 (manifest hash rehydrate test) | `DONE` | web reducer hash-change rehydrate + 단위테스트 추가 |
| F-05 (partial/unknown fallback tests) | `DONE` | selector/manifest 파서 회귀 + Playwright matrix fixture(`parameter_matrix_economy_dice_2seat`) + backend matrix 테스트까지 완료 |
| F-06 (rule-id vs label separation) | `PARTIAL` | decoupling 설계 원칙 반영, 엔진 전체 라우팅 ID 전환은 후속 |
