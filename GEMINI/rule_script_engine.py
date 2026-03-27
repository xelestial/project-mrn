from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARG_NAME_MAP: dict[str, list[str]] = {
    "landing.f.resolve": ["state", "player", "pos", "cell"],
    "game.end.evaluate": ["state"],
    "fortune.cleanup.resolve": ["state", "targets", "multiplier", "payout", "name"],
}


class RuleScriptEngine:
    """JSON-driven rule scripting for selected high-level events.

    This is intentionally minimal and safe: only supported actions are executable,
    and scripts can participate in existing event boundaries without replacing the
    whole engine with a general-purpose interpreter.
    """

    def __init__(self, engine, path: str | None) -> None:
        self.engine = engine
        self.path = path
        self.scripts = self._load(path) if path else {}

    def _load(self, path: str) -> dict[str, list[dict[str, Any]]]:
        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): list(v) for k, v in data.get("events", {}).items()}

    def _resolve_ref(self, ref: Any, context: dict[str, Any]) -> Any:
        if not isinstance(ref, str):
            return ref
        if not ref.startswith("$"):
            return ref
        parts = ref[1:].split(".")
        current: Any = context
        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            else:
                current = getattr(current, part)
        return current

    def _matches(self, rule: dict[str, Any], context: dict[str, Any]) -> bool:
        for key, expected in rule.get("when", {}).items():
            actual = self._resolve_ref(f"${key}", context)
            resolved_expected = self._resolve_ref(expected, context)
            if actual != resolved_expected:
                return False
        return True

    def execute(self, event_name: str, *args: Any, **kwargs: Any) -> Any:
        rules = self.scripts.get(event_name)
        if not rules:
            return None
        arg_names = ARG_NAME_MAP.get(event_name, [])
        context: dict[str, Any] = {name: value for name, value in zip(arg_names, args)}
        context.update(kwargs)
        context.setdefault("result", {})
        for rule in rules:
            if not self._matches(rule, context):
                continue
            for action in rule.get("actions", []):
                self._apply_action(event_name, action, context)
            if rule.get("return") == "result":
                return context["result"]
            if rule.get("return") == "bool_true":
                return True
        return None

    def _apply_action(self, event_name: str, action: dict[str, Any], context: dict[str, Any]) -> None:
        atype = action["type"]
        if atype == "track_strategy_stat":
            player = context["player"]
            stat = action["stat"]
            delta = self._resolve_ref(action.get("delta", 1), context)
            self.engine._strategy_stats[player.player_id][stat] += delta
            return
        if atype == "change_f":
            actor = context.get(action.get("target", "player")) if action.get("target") else context.get("player")
            actor_pid = getattr(actor, "player_id", None)
            self.engine._change_f(
                context["state"],
                self._resolve_ref(action["amount"], context),
                reason="rule_script",
                source=event_name,
                actor_pid=actor_pid,
                extra={"script_action": action.get("type")},
            )
            return
        if atype == "change_shards":
            target = context[action.get("target", "player")]
            target.shards += self._resolve_ref(action["amount"], context)
            return
        if atype == "set_result":
            payload = action.get("value", {})
            for key, value in payload.items():
                context["result"][key] = self._resolve_ref(value, context)
            return
        if atype == "apply_same_tile_bonus":
            context["result"] = self.engine._apply_weather_same_tile_bonus(context["state"], context["player"], dict(context["result"]))
            return
        if atype == "evaluate_end_rules":
            end_reason = self.engine._evaluate_end_rules(context["state"])
            if end_reason is not None:
                context["state"].end_reason = end_reason
                context["result"]["end_reason"] = end_reason
            return
        if atype == "cleanup_burdens":
            state = context["state"]
            targets = context["targets"]
            multiplier = int(self._resolve_ref(action.get("multiplier", "$multiplier"), context))
            payout = bool(self._resolve_ref(action.get("payout", "$payout"), context))
            name = str(self._resolve_ref(action.get("name", "$name"), context))
            context["result"] = self.engine._default_fortune_burden_cleanup(state, targets, multiplier, payout, name)
            return
        raise ValueError(f"Unsupported rule-script action: {atype}")
