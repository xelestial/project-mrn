# 플레이어별 독립 AI 모듈 아키텍처 계획

**작성**: Claude Sonnet 4.6
**날짜**: 2026-03-27
**목표**: 각 플레이어가 별도의 AI 모듈(Claude, GPT, Random 등)을 독립적으로 갖는 구조

---

## 1. 현재 구조의 문제

```
GameEngine
  └── self.policy: BasePolicy  ← 단일 policy 객체가 4명 전부 담당
        └── ArenaPolicy
              ├── player 1 → HeuristicPolicy("aggressive")
              ├── player 2 → HeuristicPolicy("v3_claude")
              ├── player 3 → HeuristicPolicy("control")
              └── player 4 → HeuristicPolicy("balanced")
```

- `ArenaPolicy`가 내부적으로 per-player routing을 하긴 하지만,
  모든 플레이어가 동일한 `CLAUDE/ai_policy.py`에서 온 `HeuristicPolicy`
- GPT의 `HeuristicPolicy` (GPT/ai_policy.py) 를 Player 2로 투입할 방법 없음
- `GameEngine`은 `self.policy.choose_*(state, player, ...)` 를 단일 객체에 위임

---

## 2. 설계 원칙

1. **독립성**: 각 플레이어 AI는 서로 다른 모듈에서 로드될 수 있다
2. **엔진 불변**: `GameEngine` 코드를 수정하지 않는다 (COLLAB_SPEC 준수)
3. **공용 허용**: 코드 재사용은 가능하지만 인터페이스 레벨에서 독립적
4. **확장성**: 3번째 AI (Gemini 등) 추가 시 기존 코드 수정 불필요

---

## 3. 핵심 아이디어: `MultiAgentDispatcher`

```
GameEngine
  └── self.policy: MultiAgentDispatcher (BasePolicy 상속)
        ├── player 1 → ClaudePolicy (CLAUDE/ai_policy.HeuristicPolicy)
        ├── player 2 → GptPolicy    (GPT/ai_policy.HeuristicPolicy)
        ├── player 3 → ClaudePolicy (다른 프로파일)
        └── player 4 → RandomPolicy
```

`MultiAgentDispatcher`는 `BasePolicy`를 상속해 `choose_*` 메서드를 모두 구현하되,
내부에서 `player.player_id`를 보고 해당 플레이어의 policy 인스턴스로 위임한다.

엔진 입장에서는 여전히 단일 `policy` 객체 — 수정 불필요.

---

## 4. 구현 계획

### Phase A: 인터페이스 정의 (`CLAUDE/multi_agent/`)

```
CLAUDE/multi_agent/
  __init__.py
  base_agent.py       ← AbstractPlayerAgent 인터페이스
  dispatcher.py       ← MultiAgentDispatcher
  agent_loader.py     ← AI 모듈을 동적으로 로드하는 팩토리
```

#### `base_agent.py`
```python
from abc import ABC, abstractmethod

class AbstractPlayerAgent(ABC):
    """각 플레이어 AI가 구현해야 하는 인터페이스."""

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """예: 'claude_v3', 'gpt_v3', 'random'"""

    # GameEngine이 호출하는 모든 choose_* 메서드를 추상 메서드로 선언
    @abstractmethod
    def choose_movement(self, state, player): ...
    @abstractmethod
    def choose_draft_card(self, state, player, pool): ...
    @abstractmethod
    def choose_final_character(self, state, player, drafted): ...
    @abstractmethod
    def choose_lap_reward(self, state, player, choices): ...
    @abstractmethod
    def choose_trick_to_use(self, state, player, hand): ...
    @abstractmethod
    def choose_mark_target(self, state, player, char): ...
    @abstractmethod
    def choose_geo_bonus(self, state, player, char): ...
    @abstractmethod
    def choose_coin_placement_tile(self, state, player): ...
    # ... (엔진이 호출하는 전체 choose_* 목록 반영)

    def set_rng(self, rng) -> None:
        pass
```

#### `dispatcher.py`
```python
from CLAUDE.ai_policy import BasePolicy

class MultiAgentDispatcher(BasePolicy):
    """
    플레이어별 독립 AI를 단일 policy 인터페이스로 노출.
    GameEngine은 이 객체만 보고, 실제 결정은 각 플레이어의 agent로 위임.
    """

    def __init__(self, agents: dict[int, AbstractPlayerAgent]):
        super().__init__()
        # player_id(1-indexed) → agent
        self._agents: dict[int, AbstractPlayerAgent] = agents

    def set_rng(self, rng) -> None:
        for agent in self._agents.values():
            agent.set_rng(rng)

    def _agent(self, player) -> AbstractPlayerAgent:
        return self._agents[player.player_id + 1]

    def choose_movement(self, state, player):
        return self._agent(player).choose_movement(state, player)

    def choose_draft_card(self, state, player, pool):
        return self._agent(player).choose_draft_card(state, player, pool)

    # ... 나머지 choose_* 전부 위임

    def agent_id_for_player(self, player_id: int) -> str:
        return self._agents[player_id].agent_id
```

---

### Phase B: 기존 Policy를 Agent로 래핑

#### Claude Agent (`CLAUDE/multi_agent/claude_agent.py`)
```python
from CLAUDE.ai_policy import HeuristicPolicy
from .base_agent import AbstractPlayerAgent

class ClaudePlayerAgent(AbstractPlayerAgent):
    """Claude HeuristicPolicy를 AbstractPlayerAgent로 래핑."""

    def __init__(self, profile: str = "heuristic_v2_v3_claude"):
        self._policy = HeuristicPolicy(character_policy_mode=profile,
                                        lap_policy_mode=profile)
        self._profile = profile

    @property
    def agent_id(self) -> str:
        return f"claude_{self._profile}"

    def choose_movement(self, state, player):
        return self._policy.choose_movement(state, player)

    # ... 나머지 위임
```

#### GPT Agent (`CLAUDE/multi_agent/gpt_agent.py`)
```python
import sys, os
# GPT 모듈 경로 주입 (엔진은 CLAUDE/ 기준이므로)
_GPT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'GPT')
sys.path.insert(0, _GPT_DIR)

from ai_policy import HeuristicPolicy as GptHeuristicPolicy
from .base_agent import AbstractPlayerAgent

class GptPlayerAgent(AbstractPlayerAgent):
    """GPT HeuristicPolicy를 AbstractPlayerAgent로 래핑."""

    def __init__(self, profile: str = "heuristic_v2_v3_gpt"):
        self._policy = GptHeuristicPolicy(character_policy_mode=profile,
                                           lap_policy_mode=profile)
        self._profile = profile

    @property
    def agent_id(self) -> str:
        return f"gpt_{self._profile}"

    # ... 나머지 위임
```

---

### Phase C: Agent Loader (팩토리)

```python
# agent_loader.py
def make_agent(spec: str) -> AbstractPlayerAgent:
    """
    spec 형식: "claude:v3_claude", "gpt:v3_gpt", "random", "claude:balanced"

    Examples:
        make_agent("claude:v3_claude")  → ClaudePlayerAgent("heuristic_v2_v3_claude")
        make_agent("gpt:v3_gpt")        → GptPlayerAgent("heuristic_v2_v3_gpt")
        make_agent("random")            → RandomPlayerAgent()
    """
    if ":" in spec:
        source, profile = spec.split(":", 1)
    else:
        source, profile = spec, None

    if source == "claude":
        return ClaudePlayerAgent(f"heuristic_v2_{profile}" if profile else "heuristic_v2_v3_claude")
    elif source == "gpt":
        return GptPlayerAgent(f"heuristic_v2_{profile}" if profile else "heuristic_v2_v3_gpt")
    elif source == "random":
        return RandomPlayerAgent()
    else:
        raise ValueError(f"Unknown agent source: {source}")
```

---

### Phase D: 대결 실행 스크립트 (`CLAUDE/battle.py`)

```bash
# Claude v3 vs GPT v3 (1v1, 나머지 2명은 balanced 기준선)
python battle.py \
  --player1 claude:v3_claude \
  --player2 gpt:v3_gpt \
  --player3 claude:balanced \
  --player4 claude:balanced \
  --simulations 500 --seed 42

# 4인 자유대결
python battle.py \
  --player1 claude:v3_claude \
  --player2 gpt:v3_gpt \
  --player3 claude:aggressive \
  --player4 random \
  --simulations 200
```

출력: 기존 `simulate_with_logs.py` 포맷 + `agent_id` 필드 추가
통계: `policy_stats`를 `agent_id` 기준으로 집계

---

## 5. API 호환성 검토

GPT `HeuristicPolicy`의 `choose_*` 시그니처가 Claude와 동일한지 확인 필요:

| 메서드 | Claude 시그니처 | GPT 동일 여부 |
|---|---|---|
| `choose_movement` | `(state, player)` | 확인 필요 |
| `choose_draft_card` | `(state, player, pool)` | 확인 필요 |
| `choose_lap_reward` | `(state, player, choices)` | 확인 필요 |
| `choose_trick_to_use` | `(state, player, hand)` | 확인 필요 |

불일치 시 각 `GptPlayerAgent` 메서드에서 인자 변환 처리.

---

## 6. 작업 순서

```
[A] multi_agent/base_agent.py     — AbstractPlayerAgent 인터페이스
[B] multi_agent/claude_agent.py   — Claude wrapper
[C] API 호환성 확인 (GPT ai_policy.py 메서드 시그니처)
[D] multi_agent/gpt_agent.py      — GPT wrapper + 경로 주입
[E] multi_agent/dispatcher.py     — MultiAgentDispatcher
[F] multi_agent/agent_loader.py   — 팩토리
[G] battle.py                     — 대결 실행 스크립트
[H] 100게임 테스트 후 PR
```

---

## 7. 비고

- **엔진 불변 원칙 준수**: `GameEngine`, `engine.py` 수정 없음
- **공용 코드 허용**: `BasePolicy`, `survival_common` 등 공유 가능,
  단 각 AI의 `choose_*` 결정 경로는 독립된 클래스로 분리
- **통계 호환**: 기존 `RunningSummary` 포맷 유지, `agent_id` 필드만 추가
- **Gemini 확장**: `GeminiPlayerAgent` 추가만으로 4번째 AI 참전 가능
