# [COMPLETE] 플레이어별 독립 AI 모듈 구현 명세

**구현**: Claude Sonnet 4.6 (CLAUDE-MAIN 브랜치)
**완료일**: 2026-03-27
**테스트**: 128 passed / 에러 0

GPT가 동일한 구조를 GPT/ 디렉토리에 구현하기 위한 완전한 명세.

---

## 구현된 파일 목록

```
CLAUDE/
  multi_agent/
    __init__.py
    base_agent.py       ← AbstractPlayerAgent 인터페이스
    claude_agent.py     ← Claude HeuristicPolicy 래퍼
    gpt_agent.py        ← GPT HeuristicPolicy 격리 로드 래퍼
    dispatcher.py       ← MultiAgentDispatcher (BasePolicy 상속)
    agent_loader.py     ← make_agent() 팩토리
  battle.py             ← CLI 대결 실행기
  test_multi_agent.py   ← 11개 통합 테스트
```

---

## 핵심 설계 결정

### 1. 엔진 불변 원칙 준수

`GameEngine`은 `self.policy: BasePolicy`를 단일 객체로만 본다.
`MultiAgentDispatcher`가 `BasePolicy`를 상속하여 엔진 코드를 수정하지 않는다.

```python
engine = GameEngine(config, MultiAgentDispatcher(agents), rng=rng)
```

### 2. GPT 모듈 격리 로드 (`gpt_agent.py`)

CLAUDE와 GPT의 `survival_common.py`가 다르다 (GPT에 `CleanupStrategyContext` 추가).
같은 프로세스에서 두 버전을 공존시키기 위해 `sys.modules` 교체 방식 사용:

```python
_GPT_OWN_MODULES = [
    "survival_common", "policy_groups", "policy_mark_utils",
    "policy_hooks", "ai_policy",
    "policy", "policy.profile", "policy.profile.spec",
    "policy.profile.registry", "policy.profile.presets",
]

def _load_gpt_policy_class():
    # 1. CLAUDE 버전 저장 & sys.modules에서 제거
    saved = {k: sys.modules.pop(k) for k in _GPT_OWN_MODULES if k in sys.modules}
    # 2. GPT 경로 우선삽입 + cwd 변경
    sys.path.insert(0, _GPT_DIR); os.chdir(_GPT_DIR)
    try:
        import ai_policy as _gpt_ai_policy
        return _gpt_ai_policy.HeuristicPolicy
    finally:
        # 3. GPT 버전 제거, CLAUDE 버전 복원
        for k in _GPT_OWN_MODULES: sys.modules.pop(k, None)
        sys.modules.update(saved)
        sys.path.remove(_GPT_DIR); os.chdir(orig_cwd)
```

로드된 `GptHeuristicPolicy` 인스턴스는 GPT의 globals를 참조하므로 복원 후에도 GPT 로직으로 동작한다.

### 3. 라우팅: player_id 기반

엔진은 `choose_*(state, player, ...)` 형태로 호출.
`player.player_id`는 0-indexed이므로 dispatcher 내부에서 `+1` 변환.

```python
def _a(self, player) -> AbstractPlayerAgent:
    return self._agents[player.player_id + 1]  # 1-indexed

def choose_movement(self, state, player):
    return self._a(player).choose_movement(state, player)
```

---

## GPT 구현 지침

GPT가 동일하게 구현할 내용은 `GPT/multi_agent/` 디렉토리에 미러링한다.

### base_agent.py — 동일하게 복사

`AbstractPlayerAgent` 인터페이스는 동일. 엔진 호출 표면이 같으므로 그대로 사용.

### gpt_agent.py → claude_agent.py (역할 반전)

GPT 구현에서는 `ClaudePlayerAgent`가 격리 로드 대상이 된다.

```python
_CLAUDE_DIR = os.path.normpath(os.path.join(_GPT_DIR, "..", "CLAUDE"))

_CLAUDE_OWN_MODULES = [
    "survival_common", "policy_groups", "policy_mark_utils",
    "policy_hooks", "ai_policy",
    "policy", "policy.profile", "policy.profile.spec",
    "policy.profile.registry", "policy.profile.presets",
]

def _load_claude_policy_class():
    saved = {k: sys.modules.pop(k) for k in _CLAUDE_OWN_MODULES if k in sys.modules}
    sys.path.insert(0, _CLAUDE_DIR); os.chdir(_CLAUDE_DIR)
    try:
        import ai_policy as _claude_ai_policy
        return _claude_ai_policy.HeuristicPolicy
    finally:
        for k in _CLAUDE_OWN_MODULES: sys.modules.pop(k, None)
        sys.modules.update(saved)
        sys.path.remove(_CLAUDE_DIR); os.chdir(orig_cwd)
```

### dispatcher.py — GPT의 BasePolicy 상속으로 교체

CLAUDE의 `BasePolicy`는 GPT의 것과 다를 수 있으므로, GPT 구현 dispatcher는 GPT `BasePolicy`를 상속한다.

```python
# GPT/multi_agent/dispatcher.py
from ai_policy import BasePolicy  # GPT 버전
```

### agent_loader.py

```python
def make_agent(spec: str) -> AbstractPlayerAgent:
    source, profile = spec.split(":", 1) if ":" in spec else (spec, None)
    if source == "gpt":
        return GptPlayerAgent(profile or "heuristic_v3_gpt")
    elif source == "claude":
        return ClaudePlayerAgent(profile or "heuristic_v2_v3_claude")
    else:
        raise ValueError(f"Unknown source: {source}")
```

### battle.py

GPT 구현의 `battle.py`도 동일한 CLI 인터페이스:
```bash
python battle.py --player1 gpt:v3_gpt --player2 claude:v3_claude \
                 --player3 gpt:balanced --player4 gpt:balanced \
                 --simulations 100 --seed 42
```

---

## 엔진이 호출하는 choose_* 전체 목록 (API 계약)

두 구현 모두 이 메서드를 반드시 위임해야 한다.

| 메서드 | 시그니처 |
|---|---|
| `choose_movement` | `(state, player) → MovementDecision` |
| `choose_draft_card` | `(state, player, offered_cards: list[int]) → int` |
| `choose_final_character` | `(state, player, card_choices: list[int]) → str` |
| `choose_lap_reward` | `(state, player) → LapRewardDecision` |
| `choose_trick_to_use` | `(state, player, hand: list[TrickCard]) → TrickCard\|None` |
| `choose_hidden_trick_card` | `(state, player, hand: list[TrickCard]) → TrickCard\|None` |
| `choose_mark_target` | `(state, player, actor_name: str) → str\|None` |
| `choose_coin_placement_tile` | `(state, player) → int\|None` |
| `choose_geo_bonus` | `(state, player, char: str) → str` |
| `choose_doctrine_relief_target` | `(state, player, candidates: list) → int\|None` |
| `choose_purchase_tile` *(hasattr)* | `(state, player, pos, cell, cost, *, source) → bool` |
| `choose_specific_trick_reward` *(hasattr)* | `(state, player, choices) → TrickCard\|None` |
| `choose_burden_exchange_on_supply` *(hasattr)* | `(state, player, card) → bool` |
| `choose_active_flip_card` *(hasattr)* | `(state, player, flippable_cards) → int\|None` |

---

## 100게임 결과 (seed=42, Claude-MAIN 엔진)

```
Player 1: claude:heuristic_v2_v3_claude  → 26%  avg_score=2.76
Player 2: gpt:heuristic_v3_gpt           → 31%  avg_score=2.86
Player 3: claude:heuristic_v2_balanced   → 22%  avg_score=2.50
Player 4: claude:heuristic_v2_balanced   → 21%
```

GPT v3 프로파일(combo=2.15 특화)이 Claude v3(meta+disruption 균형)을 5%p 앞섰다.

---

## 테스트 체크리스트

GPT 구현 완료 기준:

- [ ] `make_agent("gpt:v3_gpt")` → `GptPlayerAgent` 반환
- [ ] `make_agent("claude:v3_claude")` → `ClaudePlayerAgent` (격리 로드) 반환
- [ ] `MultiAgentDispatcher({1: gpt_agent, 2: claude_agent, ...})` 구성 성공
- [ ] `dispatcher.set_rng(rng)` 모든 agent에 전파
- [ ] 1게임 에러 없이 완주
- [ ] 100게임 에러 0건
