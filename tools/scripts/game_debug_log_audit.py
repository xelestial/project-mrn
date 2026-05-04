from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


RUN_DIR_RE = re.compile(r"^\d{8}-\d{6}-\d{6}-p\d+$")
COMPONENTS = ("frontend", "backend", "engine")
FINAL_CHARACTER_REQUEST_TYPES = {"final_character", "final_character_choice", "character_final"}
DRAFT_REQUEST_TYPES = {"draft_card", "character_draft", "draft_character"}
CARD_FLIP_EVENTS = {"marker_flip", "active_flip"}


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    component: str = ""
    session_id: str = ""
    request_id: str = ""
    source: str = ""


def audit_debug_log_run(path: str | Path) -> dict[str, Any]:
    run_dir = resolve_run_dir(path)
    rows, parse_issues = _load_rows(run_dir)
    issues: list[AuditIssue] = list(parse_issues)
    warnings: list[AuditIssue] = []
    if not RUN_DIR_RE.match(run_dir.name):
        warnings.append(
            AuditIssue(
                severity="warning",
                code="non_timestamp_run_directory",
                message="debug log run directory is not timestamp-shaped; this is expected only when MRN_DEBUG_GAME_LOG_RUN_ID is explicit",
                source=str(run_dir),
            )
        )
    issues.extend(_audit_timestamp_fields(rows))
    issues.extend(_audit_frontend_duplicate_decisions(rows))
    issues.extend(_audit_backend_duplicate_accepts(rows))
    issues.extend(_audit_draft_choice_survives_final_prompt(rows))
    issues.extend(_audit_forbidden_runtime_signals(rows))
    counts = {
        "rows": len(rows),
        "frontend": sum(1 for row in rows if row.get("component") == "frontend"),
        "backend": sum(1 for row in rows if row.get("component") == "backend"),
        "engine": sum(1 for row in rows if row.get("component") == "engine"),
        "violations": sum(1 for issue in issues if issue.severity == "error"),
        "warnings": len(warnings),
    }
    return {
        "ok": counts["violations"] == 0,
        "run_dir": str(run_dir),
        "counts": counts,
        "violations": [asdict(issue) for issue in issues if issue.severity == "error"],
        "warnings": [asdict(issue) for issue in warnings],
    }


def resolve_run_dir(path: str | Path) -> Path:
    target = Path(path)
    candidates = [item for item in target.iterdir() if item.is_dir()] if target.exists() and target.is_dir() else []
    candidates = [item for item in candidates if any((item / f"{component}.jsonl").exists() for component in COMPONENTS)]
    if candidates and not RUN_DIR_RE.match(target.name):
        return max(candidates, key=lambda item: item.stat().st_mtime)
    if any((target / f"{component}.jsonl").exists() for component in COMPONENTS):
        return target
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime)
    raise FileNotFoundError(f"no debug log run found at {target}")


def _load_rows(run_dir: Path) -> tuple[list[dict[str, Any]], list[AuditIssue]]:
    rows: list[dict[str, Any]] = []
    issues: list[AuditIssue] = []
    for component in COMPONENTS:
        path = run_dir / f"{component}.jsonl"
        if not path.exists():
            continue
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                issues.append(
                    AuditIssue(
                        severity="error",
                        code="invalid_jsonl",
                        message=str(exc),
                        component=component,
                        source=f"{path}:{line_no}",
                    )
                )
                continue
            if not isinstance(row, dict):
                issues.append(
                    AuditIssue(
                        severity="error",
                        code="invalid_log_row",
                        message="debug log row must be a JSON object",
                        component=component,
                        source=f"{path}:{line_no}",
                    )
                )
                continue
            row.setdefault("component", component)
            row["_source"] = f"{path}:{line_no}"
            rows.append(row)
    return rows, issues


def _audit_timestamp_fields(rows: Iterable[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in rows:
        if row.get("ts") and isinstance(row.get("ts_ms"), int):
            continue
        issues.append(
            AuditIssue(
                severity="error",
                code="missing_timestamp_fields",
                message="debug log row must include both ts and integer ts_ms",
                component=str(row.get("component") or ""),
                session_id=str(row.get("session_id") or ""),
                request_id=_request_id(row),
                source=str(row.get("_source") or ""),
            )
        )
    return issues


def _audit_frontend_duplicate_decisions(rows: Iterable[dict[str, Any]]) -> list[AuditIssue]:
    sent_by_request: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("component") != "frontend" or row.get("event") != "decision_sent":
            continue
        payload = _payload(row)
        key = (
            str(row.get("session_id") or ""),
            str(payload.get("player_id") or ""),
            str(payload.get("request_id") or ""),
        )
        if key[2]:
            sent_by_request[key].append(row)
    issues: list[AuditIssue] = []
    for (session_id, player_id, request_id), sent_rows in sent_by_request.items():
        if len(sent_rows) <= 1:
            continue
        choices = sorted({str(_payload(row).get("choice_id") or "") for row in sent_rows})
        issues.append(
            AuditIssue(
                severity="error",
                code="frontend_duplicate_decision_sent",
                message=f"frontend sent request {request_id} {len(sent_rows)} times for P{player_id}; choices={choices}",
                component="frontend",
                session_id=session_id,
                request_id=request_id,
                source=", ".join(str(row.get("_source") or "") for row in sent_rows[:3]),
            )
        )
    return issues


def _audit_backend_duplicate_accepts(rows: Iterable[dict[str, Any]]) -> list[AuditIssue]:
    accepts_by_request: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("component") != "backend" or row.get("event") != "decision_received":
            continue
        if str(row.get("status") or "") != "accepted":
            continue
        key = (
            str(row.get("session_id") or ""),
            str(row.get("player_id") or ""),
            str(row.get("request_id") or ""),
        )
        if key[2]:
            accepts_by_request[key].append(row)
    issues: list[AuditIssue] = []
    for (session_id, player_id, request_id), accepted_rows in accepts_by_request.items():
        if len(accepted_rows) <= 1:
            continue
        issues.append(
            AuditIssue(
                severity="error",
                code="backend_duplicate_decision_accept",
                message=f"backend accepted request {request_id} {len(accepted_rows)} times for P{player_id}",
                component="backend",
                session_id=session_id,
                request_id=request_id,
                source=", ".join(str(row.get("_source") or "") for row in accepted_rows[:3]),
            )
        )
    return issues


def _audit_draft_choice_survives_final_prompt(rows: Iterable[dict[str, Any]]) -> list[AuditIssue]:
    prompt_by_request: dict[tuple[str, str], dict[str, Any]] = {}
    prompts_by_session_player: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        prompt = _frontend_prompt(row)
        if prompt is None:
            continue
        session_id = str(row.get("session_id") or "")
        request_id = str(prompt.get("request_id") or "")
        player_id = str(prompt.get("player_id") or "")
        if request_id:
            prompt_by_request[(session_id, request_id)] = prompt
        if session_id and player_id:
            prompts_by_session_player[(session_id, player_id)].append(prompt)

    issues: list[AuditIssue] = []
    for row in rows:
        if row.get("component") != "frontend" or row.get("event") != "decision_sent":
            continue
        payload = _payload(row)
        session_id = str(row.get("session_id") or "")
        request_id = str(payload.get("request_id") or "")
        choice_id = str(payload.get("choice_id") or "")
        player_id = str(payload.get("player_id") or "")
        draft_prompt = prompt_by_request.get((session_id, request_id))
        if not draft_prompt or str(draft_prompt.get("request_type") or "") not in DRAFT_REQUEST_TYPES:
            continue
        final_prompt = _first_final_prompt(prompts_by_session_player.get((session_id, player_id), []), request_id)
        if final_prompt is None:
            continue
        final_choices = _prompt_choice_ids(final_prompt)
        if choice_id and choice_id not in final_choices:
            issues.append(
                AuditIssue(
                    severity="error",
                    code="draft_choice_missing_from_final_prompt",
                    message=f"draft choice {choice_id} from {request_id} is missing from final character prompt {final_prompt.get('request_id')}",
                    component="frontend",
                    session_id=session_id,
                    request_id=request_id,
                    source=str(row.get("_source") or ""),
                )
            )
    return issues


def _prompt_choice_ids(prompt: dict[str, Any]) -> set[str]:
    choice_ids: set[str] = set()

    def add_choice(value: Any) -> None:
        if isinstance(value, (str, int)):
            choice_ids.add(str(value))
            return
        if not isinstance(value, dict):
            return
        for key in ("id", "choice_id", "card_index"):
            if value.get(key) not in (None, ""):
                choice_ids.add(str(value[key]))
        nested_value = value.get("value")
        if isinstance(nested_value, dict) and nested_value.get("card_index") not in (None, ""):
            choice_ids.add(str(nested_value["card_index"]))

    def add_choices(values: Any) -> None:
        if isinstance(values, list):
            for value in values:
                add_choice(value)

    add_choices(prompt.get("choices"))
    add_choices(prompt.get("legal_choices"))
    add_choices(_get_path(prompt, ("surface", "character_pick", "options")))
    add_choices(_get_path(prompt, ("prompt", "active", "choices")))
    add_choices(_get_path(prompt, ("prompt", "active", "surface", "character_pick", "options")))
    add_choices(_get_path(prompt, ("view_state", "prompt", "active", "choices")))
    add_choices(_get_path(prompt, ("view_state", "prompt", "active", "surface", "character_pick", "options")))
    add_choices(_get_path(prompt, ("public_context", "choice_faces")))
    add_choices(_get_path(prompt, ("prompt", "active", "public_context", "choice_faces")))
    add_choices(_get_path(prompt, ("view_state", "prompt", "active", "public_context", "choice_faces")))
    return choice_ids


def _get_path(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _audit_forbidden_runtime_signals(rows: Iterable[dict[str, Any]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for row in rows:
        component = str(row.get("component") or "")
        event = str(row.get("event") or "")
        module_type = _module_type(row)
        if module_type == "LegacyActionAdapterModule":
            issues.append(
                AuditIssue(
                    severity="error",
                    code="legacy_action_adapter_signal",
                    message="LegacyActionAdapterModule appeared in debug logs",
                    component=component,
                    session_id=str(row.get("session_id") or ""),
                    request_id=_request_id(row),
                    source=str(row.get("_source") or ""),
                )
            )
        if event == "runtime_failed" and "RoundEndCardFlipModule cannot be emitted from active turn context" in str(row.get("error") or ""):
            issues.append(
                AuditIssue(
                    severity="error",
                    code="round_end_flip_active_turn_violation",
                    message="backend semantic guard observed a card flip emitted from active turn context",
                    component=component,
                    session_id=str(row.get("session_id") or ""),
                    source=str(row.get("_source") or ""),
                )
            )
        if component == "engine" and event in CARD_FLIP_EVENTS and module_type != "RoundEndCardFlipModule":
            issues.append(
                AuditIssue(
                    severity="error",
                    code="card_flip_wrong_module",
                    message=f"{event} must be emitted by RoundEndCardFlipModule, got {module_type or '-'}",
                    component=component,
                    session_id=str(row.get("session_id") or ""),
                    source=str(row.get("_source") or ""),
                )
            )
    return issues


def _first_final_prompt(prompts: list[dict[str, Any]], draft_request_id: str) -> dict[str, Any] | None:
    found_draft = False
    for prompt in prompts:
        if str(prompt.get("request_id") or "") == draft_request_id:
            found_draft = True
            continue
        if found_draft and str(prompt.get("request_type") or "") in FINAL_CHARACTER_REQUEST_TYPES:
            return prompt
    return None


def _frontend_prompt(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("component") != "frontend" or row.get("event") != "stream_message":
        return None
    payload = _payload(row)
    if payload.get("type") != "prompt":
        return None
    prompt = payload.get("payload")
    return prompt if isinstance(prompt, dict) else None


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _request_id(row: dict[str, Any]) -> str:
    direct = row.get("request_id")
    if direct:
        return str(direct)
    payload = _payload(row)
    if payload.get("request_id"):
        return str(payload.get("request_id"))
    nested = payload.get("payload")
    if isinstance(nested, dict) and nested.get("request_id"):
        return str(nested.get("request_id"))
    return ""


def _module_type(row: dict[str, Any]) -> str:
    direct = row.get("module_type")
    if direct:
        return str(direct)
    payload = _payload(row)
    runtime_module = payload.get("runtime_module")
    if isinstance(runtime_module, dict) and runtime_module.get("module_type"):
        return str(runtime_module.get("module_type"))
    nested = payload.get("payload")
    if isinstance(nested, dict):
        runtime_module = nested.get("runtime_module")
        if isinstance(runtime_module, dict) and runtime_module.get("module_type"):
            return str(runtime_module.get("module_type"))
        if nested.get("module_type"):
            return str(nested.get("module_type"))
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit MRN frontend/backend/engine debug log runs for turn-flow violations.")
    parser.add_argument("path", nargs="?", default=".log", help="debug log run directory, or a parent directory containing timestamped runs")
    parser.add_argument("--no-fail", action="store_true", help="always exit 0 after printing the report")
    args = parser.parse_args(argv)
    report = audit_debug_log_run(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if args.no_fail or report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
