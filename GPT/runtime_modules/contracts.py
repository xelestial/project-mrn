from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, NotRequired, TypedDict


RunnerKind = Literal["legacy", "module"]
FrameType = Literal["round", "turn", "sequence", "simultaneous"]
FrameStatus = Literal["running", "suspended", "completed", "failed"]
ModuleStatus = Literal["queued", "running", "suspended", "completed", "skipped", "failed"]
ModuleResultStatus = Literal["completed", "suspended", "failed"]
QueueOpKind = Literal["push_front", "push_back", "insert_after", "replace_current", "spawn_child_frame", "complete_frame"]
ModifierScope = Literal["single_use", "sequence", "turn", "round"]
ModifierExpiry = Literal["module_completed", "sequence_completed", "turn_completed", "round_completed"]
SimultaneousCommitPolicy = Literal["all_required", "timeout_default"]


@dataclass(slots=True)
class ModuleRef:
    module_id: str
    module_type: str
    phase: str
    owner_player_id: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    modifiers: list[str] = field(default_factory=list)
    idempotency_key: str = ""
    status: ModuleStatus = "queued"
    cursor: str = "start"
    suspension_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ModuleRef":
        return cls(
            module_id=str(payload.get("module_id", "")),
            module_type=str(payload.get("module_type", "")),
            phase=str(payload.get("phase", "")),
            owner_player_id=_optional_int(payload.get("owner_player_id")),
            payload=dict(payload.get("payload") or {}),
            modifiers=[str(item) for item in payload.get("modifiers", [])],
            idempotency_key=str(payload.get("idempotency_key", "")),
            status=_module_status(payload.get("status", "queued")),
            cursor=str(payload.get("cursor", "start") or "start"),
            suspension_id=str(payload.get("suspension_id", "")),
        )


@dataclass(slots=True)
class FrameState:
    frame_id: str
    frame_type: FrameType
    owner_player_id: int | None
    parent_frame_id: str | None
    module_queue: list[ModuleRef] = field(default_factory=list)
    active_module_id: str | None = None
    completed_module_ids: list[str] = field(default_factory=list)
    status: FrameStatus = "running"
    created_by_module_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "frame_type": self.frame_type,
            "owner_player_id": self.owner_player_id,
            "parent_frame_id": self.parent_frame_id,
            "module_queue": [module.to_payload() for module in self.module_queue],
            "active_module_id": self.active_module_id,
            "completed_module_ids": list(self.completed_module_ids),
            "status": self.status,
            "created_by_module_id": self.created_by_module_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FrameState":
        return cls(
            frame_id=str(payload.get("frame_id", "")),
            frame_type=_frame_type(payload.get("frame_type", "sequence")),
            owner_player_id=_optional_int(payload.get("owner_player_id")),
            parent_frame_id=_optional_str(payload.get("parent_frame_id")),
            module_queue=[
                ModuleRef.from_payload(item)
                for item in payload.get("module_queue", [])
                if isinstance(item, dict)
            ],
            active_module_id=_optional_str(payload.get("active_module_id")),
            completed_module_ids=[str(item) for item in payload.get("completed_module_ids", [])],
            status=_frame_status(payload.get("status", "running")),
            created_by_module_id=_optional_str(payload.get("created_by_module_id")),
        )


@dataclass(slots=True)
class ModuleJournalEntry:
    module_id: str
    frame_id: str
    status: ModuleStatus
    idempotency_key: str
    event_types: list[str] = field(default_factory=list)
    error: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ModuleJournalEntry":
        return cls(
            module_id=str(payload.get("module_id", "")),
            frame_id=str(payload.get("frame_id", "")),
            status=_module_status(payload.get("status", "completed")),
            idempotency_key=str(payload.get("idempotency_key", "")),
            event_types=[str(item) for item in payload.get("event_types", [])],
            error=str(payload.get("error", "")),
        )


@dataclass(slots=True)
class Modifier:
    modifier_id: str
    source_module_id: str
    target_module_type: str
    scope: ModifierScope
    owner_player_id: int | None
    priority: int
    payload: dict[str, Any] = field(default_factory=dict)
    propagation: list[str] = field(default_factory=list)
    expires_on: ModifierExpiry = "module_completed"
    consumed: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Modifier":
        return cls(
            modifier_id=str(payload.get("modifier_id", "")),
            source_module_id=str(payload.get("source_module_id", "")),
            target_module_type=str(payload.get("target_module_type", "")),
            scope=_modifier_scope(payload.get("scope", "single_use")),
            owner_player_id=_optional_int(payload.get("owner_player_id")),
            priority=int(payload.get("priority", 100)),
            payload=dict(payload.get("payload") or {}),
            propagation=[str(item) for item in payload.get("propagation", [])],
            expires_on=_modifier_expiry(payload.get("expires_on", "module_completed")),
            consumed=bool(payload.get("consumed", False)),
        )


@dataclass(slots=True)
class ModifierRegistryState:
    modifiers: list[Modifier] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {"modifiers": [modifier.to_payload() for modifier in self.modifiers]}

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ModifierRegistryState":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            modifiers=[
                Modifier.from_payload(item)
                for item in payload.get("modifiers", [])
                if isinstance(item, dict)
            ]
        )


@dataclass(slots=True)
class PromptContinuation:
    request_id: str
    prompt_instance_id: int
    resume_token: str
    frame_id: str
    module_id: str
    module_type: str
    player_id: int
    request_type: str
    legal_choices: list[dict[str, Any]] = field(default_factory=list)
    public_context: dict[str, Any] = field(default_factory=dict)
    expires_at_ms: int | None = None
    module_cursor: str = "start"

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "PromptContinuation | None":
        if not isinstance(payload, dict):
            return None
        return cls(
            request_id=str(payload.get("request_id", "")),
            prompt_instance_id=int(payload.get("prompt_instance_id", 0)),
            resume_token=str(payload.get("resume_token", "")),
            frame_id=str(payload.get("frame_id", "")),
            module_id=str(payload.get("module_id", "")),
            module_type=str(payload.get("module_type", "")),
            player_id=int(payload.get("player_id", 0)),
            request_type=str(payload.get("request_type", "")),
            legal_choices=[dict(item) for item in payload.get("legal_choices", []) if isinstance(item, dict)],
            public_context=dict(payload.get("public_context") or {}),
            expires_at_ms=_optional_int(payload.get("expires_at_ms")),
            module_cursor=str(payload.get("module_cursor", "start") or "start"),
        )


@dataclass(slots=True)
class SimultaneousPromptBatchContinuation:
    batch_id: str
    frame_id: str
    module_id: str
    module_type: str
    request_type: str
    participant_player_ids: list[int]
    prompts_by_player_id: dict[int, PromptContinuation]
    responses_by_player_id: dict[int, dict[str, Any]] = field(default_factory=dict)
    missing_player_ids: list[int] = field(default_factory=list)
    eligibility_snapshot: dict[str, Any] = field(default_factory=dict)
    commit_policy: SimultaneousCommitPolicy = "all_required"
    default_policy: dict[str, Any] = field(default_factory=dict)
    expires_at_ms: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "frame_id": self.frame_id,
            "module_id": self.module_id,
            "module_type": self.module_type,
            "request_type": self.request_type,
            "participant_player_ids": list(self.participant_player_ids),
            "prompts_by_player_id": {
                str(player_id): prompt.to_payload()
                for player_id, prompt in self.prompts_by_player_id.items()
            },
            "responses_by_player_id": {
                str(player_id): dict(response)
                for player_id, response in self.responses_by_player_id.items()
            },
            "missing_player_ids": list(self.missing_player_ids),
            "resume_tokens_by_player_id": {
                str(player_id): prompt.resume_token
                for player_id, prompt in self.prompts_by_player_id.items()
            },
            "eligibility_snapshot": dict(self.eligibility_snapshot),
            "commit_policy": self.commit_policy,
            "default_policy": dict(self.default_policy),
            "expires_at_ms": self.expires_at_ms,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "SimultaneousPromptBatchContinuation | None":
        if not isinstance(payload, dict):
            return None
        prompts: dict[int, PromptContinuation] = {}
        for key, value in dict(payload.get("prompts_by_player_id") or {}).items():
            prompt = PromptContinuation.from_payload(value if isinstance(value, dict) else None)
            if prompt is not None:
                prompts[int(key)] = prompt
        return cls(
            batch_id=str(payload.get("batch_id", "")),
            frame_id=str(payload.get("frame_id", "")),
            module_id=str(payload.get("module_id", "")),
            module_type=str(payload.get("module_type", "")),
            request_type=str(payload.get("request_type", "")),
            participant_player_ids=[int(item) for item in payload.get("participant_player_ids", [])],
            prompts_by_player_id=prompts,
            responses_by_player_id={
                int(key): dict(value)
                for key, value in dict(payload.get("responses_by_player_id") or {}).items()
                if isinstance(value, dict)
            },
            missing_player_ids=[int(item) for item in payload.get("missing_player_ids", [])],
            eligibility_snapshot=dict(payload.get("eligibility_snapshot") or {}),
            commit_policy=_simultaneous_commit_policy(payload.get("commit_policy", "all_required")),
            default_policy=dict(payload.get("default_policy") or {}),
            expires_at_ms=_optional_int(payload.get("expires_at_ms")),
        )


@dataclass(slots=True)
class GameRuntimeState:
    schema_version: int
    runner_kind: RunnerKind
    round_index: int
    turn_index: int
    frame_stack: list[FrameState] = field(default_factory=list)
    module_journal: list[ModuleJournalEntry] = field(default_factory=list)
    active_prompt: PromptContinuation | None = None
    active_prompt_batch: SimultaneousPromptBatchContinuation | None = None
    scheduled_turn_injections: dict[str, list[ModuleRef]] = field(default_factory=dict)
    modifier_registry: ModifierRegistryState = field(default_factory=ModifierRegistryState)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runner_kind": self.runner_kind,
            "round_index": self.round_index,
            "turn_index": self.turn_index,
            "frame_stack": [frame.to_payload() for frame in self.frame_stack],
            "module_journal": [entry.to_payload() for entry in self.module_journal],
            "active_prompt": None if self.active_prompt is None else self.active_prompt.to_payload(),
            "active_prompt_batch": None
            if self.active_prompt_batch is None
            else self.active_prompt_batch.to_payload(),
            "scheduled_turn_injections": {
                str(key): [module.to_payload() for module in modules]
                for key, modules in self.scheduled_turn_injections.items()
            },
            "modifier_registry": self.modifier_registry.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "GameRuntimeState | None":
        if not isinstance(payload, dict):
            return None
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            runner_kind="module" if payload.get("runner_kind") == "module" else "legacy",
            round_index=int(payload.get("round_index", 0)),
            turn_index=int(payload.get("turn_index", 0)),
            frame_stack=[
                FrameState.from_payload(item)
                for item in payload.get("frame_stack", [])
                if isinstance(item, dict)
            ],
            module_journal=[
                ModuleJournalEntry.from_payload(item)
                for item in payload.get("module_journal", [])
                if isinstance(item, dict)
            ],
            active_prompt=PromptContinuation.from_payload(payload.get("active_prompt")),
            active_prompt_batch=SimultaneousPromptBatchContinuation.from_payload(payload.get("active_prompt_batch")),
            scheduled_turn_injections={
                str(key): [ModuleRef.from_payload(item) for item in value if isinstance(item, dict)]
                for key, value in dict(payload.get("scheduled_turn_injections") or {}).items()
                if isinstance(value, list)
            },
            modifier_registry=ModifierRegistryState.from_payload(payload.get("modifier_registry")),
        )


@dataclass(slots=True)
class DomainEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModuleError:
    code: str
    message: str


@dataclass(slots=True)
class ModuleResult:
    status: ModuleResultStatus
    events: list[DomainEvent] = field(default_factory=list)
    queue_ops: list["QueueOp"] = field(default_factory=list)
    modifier_ops: list[dict[str, Any]] = field(default_factory=list)
    prompt: dict[str, Any] | None = None
    error: ModuleError | None = None


class QueueOp(TypedDict):
    op: QueueOpKind
    target_frame_id: str
    anchor_module_id: NotRequired[str]
    module: NotRequired[ModuleRef]
    modules: NotRequired[list[ModuleRef]]
    frame: NotRequired[FrameState]


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _frame_type(value: object) -> FrameType:
    return value if value in {"round", "turn", "sequence", "simultaneous"} else "sequence"  # type: ignore[return-value]


def _frame_status(value: object) -> FrameStatus:
    return value if value in {"running", "suspended", "completed", "failed"} else "running"  # type: ignore[return-value]


def _module_status(value: object) -> ModuleStatus:
    allowed = {"queued", "running", "suspended", "completed", "skipped", "failed"}
    return value if value in allowed else "queued"  # type: ignore[return-value]


def _modifier_scope(value: object) -> ModifierScope:
    return value if value in {"single_use", "sequence", "turn", "round"} else "single_use"  # type: ignore[return-value]


def _modifier_expiry(value: object) -> ModifierExpiry:
    allowed = {"module_completed", "sequence_completed", "turn_completed", "round_completed"}
    return value if value in allowed else "module_completed"  # type: ignore[return-value]


def _simultaneous_commit_policy(value: object) -> SimultaneousCommitPolicy:
    return value if value in {"all_required", "timeout_default"} else "all_required"  # type: ignore[return-value]
