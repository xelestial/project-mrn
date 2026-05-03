# [PATCH] CLAUDE Multi-Agent Runtime Compatibility

## 목적
- `main` 브랜치 기준에서 `GPT` 쪽 배틀 러너가 `CLAUDE` 정책을 같은 프로세스 안에서 호출할 때 발생한 런타임 충돌을 해소하기 위한 패치 제안이다.
- 이번 문서는 `CLAUDE/` 코드에 직접 남기지 않고, 이후 동기화용으로 필요한 수정 범위를 기록한다.

## 배경
- 기존 `GPT vs CLAUDE` 100게임 배틀을 `main`에서 실행하려고 하면, `CLAUDE` 정책 로딩 과정에서 모듈 충돌과 import 누락이 발생했다.
- 실제로 확인된 오류 축:
  - `policy.*` 모듈이 서로 다른 런타임에서 섞임
  - `survival_common` / `policy.registry` 등 하위 의존 모듈이 plain-name import로 잡힘
  - `game_enums` 부재로 인한 import 실패

## 필요한 변경

### 1. `CLAUDE/multi_agent/runtime_loader.py`
- isolated runtime을 로드한 뒤, 단순히 policy 객체만 반환하지 말고 `loaded_modules`를 함께 보관해야 한다.
- `LoadedPolicyRuntime.activated()` 같은 context manager를 추가해서, policy method 호출 시 아래를 잠시 적용해야 한다.
  - `sys.modules`에 plain-name alias 주입
    - `ai_policy`
    - `survival_common`
    - `policy_hooks`
    - `policy_groups`
    - `policy_mark_utils`
    - 필요한 `policy.*` 하위 모듈
  - runtime root를 `sys.path` 앞쪽에 임시 삽입
  - 종료 후 기존 `sys.modules` / `sys.path` 복원
- 핵심은 `construct-time isolation`만이 아니라 `call-time isolation`도 보장하는 것이다.

### 2. `CLAUDE/multi_agent/claude_agent.py`
- 정책 인스턴스 생성 시 `with runtime.activated():` 안에서 policy를 만들어야 한다.
- `choose_*` 계열 호출도 모두 같은 activation context 안에서 실행해야 한다.
- 즉 agent wrapper는 “policy method를 그냥 호출”하면 안 되고, 항상 runtime activation을 감싸야 한다.

### 3. `CLAUDE/multi_agent/gpt_agent.py`
- 위와 동일한 방식으로 `with runtime.activated():` 안에서 policy 생성 및 method 호출이 이뤄져야 한다.
- `GPT` 정책을 `CLAUDE` 쪽에서 감쌀 때도 같은 call-time isolation이 필요하다.

### 4. `CLAUDE/game_enums.py`
- 현재 `main` 기준에선 일부 경로가 `game_enums.CellKind`를 기대한다.
- 최소 호환 shim 파일이 필요하다.
- 제안 내용:

```python
from config import CellKind

__all__ = ["CellKind"]
```

## 구현 의도
- `CLAUDE` 정책 자체를 뜯어고치는 패치가 아니다.
- 멀티에이전트 배틀에서 서로 다른 정책 런타임을 안전하게 공존시키기 위한 호환 계층 패치다.
- `engine`, `policy logic`, `profile behavior`를 바꾸지 않고, loader / wrapper / compatibility shim에만 국한하는 것이 맞다.

## 권장 적용 순서
1. `runtime_loader.py`에 activation context 추가
2. `claude_agent.py`, `gpt_agent.py`에서 생성/호출 경로를 activation 기반으로 변경
3. `game_enums.py` shim 추가
4. `CLAUDE/test_multi_agent.py`와 `GPT/test_multi_agent.py` 재검증
5. `GPT/battle.py`에서 `claude vs gpt` smoke run 후 100게임 재검증

## 기대 결과
- `CLAUDE` 쪽 코드를 직접 장기간 수정하지 않아도 `main` 기준 `GPT vs CLAUDE` 배틀이 다시 동작한다.
- `CLAUDE` 정책과 `GPT` 정책이 같은 프로세스 안에서 모듈 충돌 없이 공존할 수 있다.
- 이후 시각화 / live spectator / human-vs-AI 작업에서도 멀티런타임 호출 안정성이 확보된다.
