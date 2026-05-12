from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class ParameterValidationError(ValueError):
    """Raised when session config cannot be resolved into safe runtime parameters."""


DEFAULT_EXTERNAL_AI_TIMEOUT_MS = 30_000


class RootSourceRegistry:
    """Canonical root-source registry for fingerprint generation."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[4]

    def list_sources(self) -> list[tuple[str, Path]]:
        engine = self._root_dir / "engine"
        return [
            ("ruleset", engine / "ruleset.json"),
            ("board_layout", engine / "board_layout.json"),
            ("characters", engine / "characters.py"),
            ("trick_cards", engine / "trick_cards.py"),
            ("weather_cards", engine / "weather_cards.py"),
            ("fortune_cards", engine / "fortune_cards.py"),
            ("config", engine / "config.py"),
        ]

    def compute_fingerprints(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, path in self.list_sources():
            result[name] = self._file_sha256(path)
        return result

    @staticmethod
    def _file_sha256(path: Path) -> str:
        if not path.exists():
            return "missing"
        sha = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()


EXTERNAL_AI_WORKER_PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "reference_heuristic": {
        "required_worker_adapter": "reference_heuristic_v1",
        "required_policy_class": "HeuristicPolicy",
        "required_decision_style": "contract_heuristic",
        "required_capabilities": [
            "choice_id_response",
            "choice_payload_echo",
            "healthcheck",
            "worker_identity",
        ],
    },
    "priority_scored": {
        "required_worker_adapter": "priority_score_v1",
        "required_policy_class": "PriorityScoredPolicy",
        "required_decision_style": "priority_scored_contract",
        "required_capabilities": [
            "choice_id_response",
            "choice_payload_echo",
            "healthcheck",
            "worker_identity",
            "priority_scored_choice",
            "scored_choice_strategy_v1",
        ],
    },
}


class GameParameterResolver:
    """Resolve session config into runtime-safe game parameter set."""

    def __init__(self, registry: RootSourceRegistry | None = None) -> None:
        self._registry = registry or RootSourceRegistry()

    def resolve(self, session_config: dict[str, Any] | None) -> dict[str, Any]:
        cfg = self._load_default_config()
        raw = dict(session_config or {})
        seat_limits = self._resolve_seat_limits(raw=raw, default_player_count=int(cfg.player_count))
        runtime = self._resolve_runtime(raw=raw, seat_limits=seat_limits)
        board_topology = self._resolve_board_topology(raw=raw)
        participant_defaults = self._resolve_participant_defaults(raw=raw)
        end_rules = self._resolve_end_rules(raw=raw, cfg=cfg)
        start_reward_rules = self._resolve_start_reward_rules(cfg=cfg)

        dice_values = raw.get("dice_values", list(cfg.dice_cards.values))
        if not isinstance(dice_values, list) or not dice_values or not all(isinstance(v, int) and v > 0 for v in dice_values):
            raise ParameterValidationError("invalid_dice_values")

        max_cards_per_turn = raw.get("dice_max_cards_per_turn", int(cfg.dice_cards.max_cards_per_turn))
        if not isinstance(max_cards_per_turn, int) or max_cards_per_turn < 1 or max_cards_per_turn > len(dice_values):
            raise ParameterValidationError("invalid_dice_max_cards_per_turn")

        starting_cash = raw.get("starting_cash", int(cfg.economy.starting_cash))
        if not isinstance(starting_cash, int) or starting_cash < 0:
            raise ParameterValidationError("invalid_starting_cash")

        starting_shards = raw.get("starting_shards", int(cfg.shards.starting_shards))
        if not isinstance(starting_shards, int) or starting_shards < 0:
            raise ParameterValidationError("invalid_starting_shards")

        tile_metadata = cfg.board.build_tile_metadata()
        labels = raw.get("labels")
        if labels is None:
            labels = {}
        if not isinstance(labels, dict):
            raise ParameterValidationError("invalid_labels")

        return {
            "version": "v1",
            "runtime": runtime,
            "participants": participant_defaults,
            "seats": seat_limits,
            "board": {
                "topology": board_topology,
                "tile_count": len(tile_metadata),
                "tiles": [
                    {
                        "tile_index": int(tile.index),
                        "tile_kind": tile.kind.name,
                        "block_id": int(tile.block_id),
                        "zone_color": tile.zone_color,
                        "purchase_cost": tile.purchase_cost,
                        "rent_cost": tile.rent_cost,
                    }
                    for tile in tile_metadata
                ],
            },
            "dice": {
                "values": list(dice_values),
                "max_cards_per_turn": int(max_cards_per_turn),
                "use_one_card_plus_one_die": bool(cfg.dice_cards.use_one_card_plus_one_die),
            },
            "economy": {
                "starting_cash": int(starting_cash),
            },
            "resources": {
                "starting_shards": int(starting_shards),
            },
            "rules": {
                "end": end_rules,
                "start_reward": start_reward_rules,
            },
            "labels": labels,
        }

    @staticmethod
    def _resolve_runtime(raw: dict[str, Any], seat_limits: dict[str, Any]) -> dict[str, Any]:
        runtime_raw = raw.get("runtime")
        if runtime_raw is None:
            runtime_raw = {}
        if not isinstance(runtime_raw, dict):
            raise ParameterValidationError("invalid_runtime_config")

        seed_raw = runtime_raw.get("seed", raw.get("seed", 42))
        if isinstance(seed_raw, bool):
            raise ParameterValidationError("invalid_runtime_seed")
        try:
            seed = int(seed_raw)
        except (TypeError, ValueError) as exc:
            raise ParameterValidationError("invalid_runtime_seed") from exc

        policy_mode_raw = runtime_raw.get("policy_mode", raw.get("policy_mode", None))
        if policy_mode_raw is None:
            policy_mode = None
        elif isinstance(policy_mode_raw, str):
            policy_mode = policy_mode_raw.strip() or None
        else:
            raise ParameterValidationError("invalid_runtime_policy_mode")

        runtime: dict[str, Any] = {
            "seed": seed,
            "policy_mode": policy_mode,
            "player_count": int(seat_limits["max"]),
        }

        runner_kind_raw = runtime_raw.get("runner_kind")
        if runner_kind_raw is not None:
            if not isinstance(runner_kind_raw, str) or not runner_kind_raw.strip():
                raise ParameterValidationError("invalid_runtime_runner_kind")
            runtime["runner_kind"] = runner_kind_raw.strip().lower()

        ai_delay_raw = runtime_raw.get("ai_decision_delay_ms")
        if ai_delay_raw is not None:
            if isinstance(ai_delay_raw, bool) or not isinstance(ai_delay_raw, int) or ai_delay_raw < 0:
                raise ParameterValidationError("invalid_runtime_ai_decision_delay_ms")
            runtime["ai_decision_delay_ms"] = int(ai_delay_raw)

        return runtime

    @staticmethod
    def _resolve_participant_defaults(raw: dict[str, Any]) -> dict[str, Any]:
        participants_raw = raw.get("participants")
        if participants_raw is None:
            participants_raw = raw.get("participant_clients")
        if participants_raw is None:
            participants_raw = {}
        if not isinstance(participants_raw, dict):
            raise ParameterValidationError("invalid_participants_config")

        external_ai_raw = participants_raw.get("external_ai") or {}
        if not isinstance(external_ai_raw, dict):
            raise ParameterValidationError("invalid_external_ai_config")

        transport = str(external_ai_raw.get("transport", "loopback")).strip().lower()
        if transport not in {"loopback", "http"}:
            raise ParameterValidationError("invalid_external_ai_transport")
        contract_version = str(external_ai_raw.get("contract_version", "v1")).strip().lower()
        if not contract_version:
            raise ParameterValidationError("invalid_external_ai_contract_version")
        expected_worker_id = external_ai_raw.get("expected_worker_id")
        if expected_worker_id is not None and (
            not isinstance(expected_worker_id, str) or not expected_worker_id.strip()
        ):
            raise ParameterValidationError("invalid_external_ai_expected_worker_id")
        auth_token = external_ai_raw.get("auth_token")
        if auth_token is not None and (
            not isinstance(auth_token, str) or not auth_token.strip()
        ):
            raise ParameterValidationError("invalid_external_ai_auth_token")
        auth_header_name = str(external_ai_raw.get("auth_header_name", "Authorization")).strip()
        if not auth_header_name:
            raise ParameterValidationError("invalid_external_ai_auth_header_name")
        auth_scheme = str(external_ai_raw.get("auth_scheme", "Bearer")).strip()
        if not auth_scheme:
            raise ParameterValidationError("invalid_external_ai_auth_scheme")

        timeout_ms = external_ai_raw.get("timeout_ms", DEFAULT_EXTERNAL_AI_TIMEOUT_MS)
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ParameterValidationError("invalid_external_ai_timeout")
        retry_count = external_ai_raw.get("retry_count", 1)
        if not isinstance(retry_count, int) or retry_count < 0:
            raise ParameterValidationError("invalid_external_ai_retry_count")
        backoff_ms = external_ai_raw.get("backoff_ms", 250)
        if not isinstance(backoff_ms, int) or backoff_ms < 0:
            raise ParameterValidationError("invalid_external_ai_backoff_ms")
        fallback_mode = str(external_ai_raw.get("fallback_mode", "local_ai")).strip().lower()
        if fallback_mode not in {"local_ai", "error"}:
            raise ParameterValidationError("invalid_external_ai_fallback_mode")
        healthcheck_path = str(external_ai_raw.get("healthcheck_path", "/health")).strip()
        if not healthcheck_path:
            raise ParameterValidationError("invalid_external_ai_healthcheck_path")
        healthcheck_ttl_ms = external_ai_raw.get("healthcheck_ttl_ms", 10000)
        if not isinstance(healthcheck_ttl_ms, int) or healthcheck_ttl_ms < 0:
            raise ParameterValidationError("invalid_external_ai_healthcheck_ttl")
        healthcheck_policy = str(external_ai_raw.get("healthcheck_policy", "auto")).strip().lower()
        if healthcheck_policy not in {"auto", "required", "disabled"}:
            raise ParameterValidationError("invalid_external_ai_healthcheck_policy")
        require_ready = external_ai_raw.get("require_ready", False)
        if not isinstance(require_ready, bool):
            raise ParameterValidationError("invalid_external_ai_require_ready")
        max_attempt_count = external_ai_raw.get("max_attempt_count", 3)
        if not isinstance(max_attempt_count, int) or max_attempt_count < 1:
            raise ParameterValidationError("invalid_external_ai_max_attempt_count")

        endpoint = external_ai_raw.get("endpoint")
        if endpoint is not None and not isinstance(endpoint, str):
            raise ParameterValidationError("invalid_external_ai_endpoint")
        required_capabilities = external_ai_raw.get("required_capabilities") or []
        if not isinstance(required_capabilities, list):
            raise ParameterValidationError("invalid_external_ai_required_capabilities")
        normalized_capabilities: list[str] = []
        for item in required_capabilities:
            if not isinstance(item, str) or not item.strip():
                raise ParameterValidationError("invalid_external_ai_required_capabilities")
            normalized_capabilities.append(item.strip())

        required_request_types = external_ai_raw.get("required_request_types") or []
        if not isinstance(required_request_types, list):
            raise ParameterValidationError("invalid_external_ai_required_request_types")
        normalized_request_types: list[str] = []
        for item in required_request_types:
            if not isinstance(item, str) or not item.strip():
                raise ParameterValidationError("invalid_external_ai_required_request_types")
            normalized_request_types.append(item.strip())
        worker_profile = external_ai_raw.get("worker_profile")
        if worker_profile is not None and (not isinstance(worker_profile, str) or not worker_profile.strip()):
            raise ParameterValidationError("invalid_external_ai_worker_profile")
        normalized_worker_profile = worker_profile.strip().lower() if isinstance(worker_profile, str) else None
        if normalized_worker_profile is not None and normalized_worker_profile not in EXTERNAL_AI_WORKER_PROFILE_PRESETS:
            raise ParameterValidationError("invalid_external_ai_worker_profile")
        required_policy_mode = external_ai_raw.get("required_policy_mode")
        if required_policy_mode is not None and (not isinstance(required_policy_mode, str) or not required_policy_mode.strip()):
            raise ParameterValidationError("invalid_external_ai_required_policy_mode")
        required_worker_adapter = external_ai_raw.get("required_worker_adapter")
        if required_worker_adapter is not None and (not isinstance(required_worker_adapter, str) or not required_worker_adapter.strip()):
            raise ParameterValidationError("invalid_external_ai_required_worker_adapter")
        required_policy_class = external_ai_raw.get("required_policy_class")
        if required_policy_class is not None and (not isinstance(required_policy_class, str) or not required_policy_class.strip()):
            raise ParameterValidationError("invalid_external_ai_required_policy_class")
        required_decision_style = external_ai_raw.get("required_decision_style")
        if required_decision_style is not None and (not isinstance(required_decision_style, str) or not required_decision_style.strip()):
            raise ParameterValidationError("invalid_external_ai_required_decision_style")

        headers = external_ai_raw.get("headers") or {}
        if not isinstance(headers, dict):
            raise ParameterValidationError("invalid_external_ai_headers")
        normalized_headers: dict[str, str] = {}
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ParameterValidationError("invalid_external_ai_headers")
            normalized_headers[key] = value

        if normalized_worker_profile is not None:
            preset = EXTERNAL_AI_WORKER_PROFILE_PRESETS[normalized_worker_profile]
            normalized_capabilities = list(
                dict.fromkeys([*preset.get("required_capabilities", []), *normalized_capabilities])
            )
            if required_worker_adapter is None:
                required_worker_adapter = str(preset.get("required_worker_adapter") or "")
            if required_policy_class is None:
                required_policy_class = str(preset.get("required_policy_class") or "")
            if required_decision_style is None:
                required_decision_style = str(preset.get("required_decision_style") or "")

        return {
            "external_ai": {
                "transport": transport,
                **({"worker_profile": normalized_worker_profile} if normalized_worker_profile is not None else {}),
                "contract_version": contract_version,
                "expected_worker_id": expected_worker_id.strip() if isinstance(expected_worker_id, str) else None,
                "auth_token": auth_token.strip() if isinstance(auth_token, str) else None,
                "auth_header_name": auth_header_name,
                "auth_scheme": auth_scheme,
                "timeout_ms": int(timeout_ms),
                "retry_count": int(retry_count),
                "backoff_ms": int(backoff_ms),
                "fallback_mode": fallback_mode,
                "healthcheck_path": healthcheck_path,
                "healthcheck_ttl_ms": int(healthcheck_ttl_ms),
                "healthcheck_policy": healthcheck_policy,
                "require_ready": require_ready,
                "max_attempt_count": int(max_attempt_count),
                "endpoint": endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None,
                "required_capabilities": normalized_capabilities,
                "required_request_types": normalized_request_types,
                "required_policy_mode": required_policy_mode.strip() if isinstance(required_policy_mode, str) else None,
                "required_worker_adapter": required_worker_adapter.strip() if isinstance(required_worker_adapter, str) else None,
                "required_policy_class": required_policy_class.strip() if isinstance(required_policy_class, str) else None,
                "required_decision_style": required_decision_style.strip() if isinstance(required_decision_style, str) else None,
                "headers": normalized_headers,
            }
        }

    @staticmethod
    def _resolve_board_topology(raw: dict[str, Any]) -> str:
        board_raw = raw.get("board")
        topology_candidate = raw.get("board_topology")
        if topology_candidate is None and isinstance(board_raw, dict):
            topology_candidate = board_raw.get("topology")
        if topology_candidate is None:
            return "ring"
        if not isinstance(topology_candidate, str):
            raise ParameterValidationError("invalid_board_topology")
        topology = topology_candidate.strip().lower()
        if topology not in {"ring", "line"}:
            raise ParameterValidationError("invalid_board_topology")
        return topology

    @staticmethod
    def _resolve_end_rules(raw: dict[str, Any], cfg: Any) -> dict[str, Any]:
        rules_raw = raw.get("rules")
        if rules_raw is None:
            rules_raw = {}
        if not isinstance(rules_raw, dict):
            raise ParameterValidationError("invalid_rules_config")

        end_raw = raw.get("end")
        if end_raw is None:
            end_raw = rules_raw.get("end")
        if end_raw is None:
            end_raw = {}
        if not isinstance(end_raw, dict):
            raise ParameterValidationError("invalid_end_rules")
        runtime_raw = raw.get("runtime")
        if runtime_raw is None:
            runtime_raw = {}
        if not isinstance(runtime_raw, dict):
            raise ParameterValidationError("invalid_runtime_config")

        default_end = cfg.rules.end

        f_threshold = end_raw.get("f_threshold", default_end.f_threshold)
        if f_threshold is not None:
            if isinstance(f_threshold, bool) or not isinstance(f_threshold, (int, float)) or float(f_threshold) <= 0:
                raise ParameterValidationError("invalid_end_f_threshold")
            f_threshold = float(f_threshold)

        monopolies = end_raw.get("monopolies_to_trigger_end", default_end.monopolies_to_trigger_end)
        if isinstance(monopolies, bool) or not isinstance(monopolies, int) or monopolies < 0:
            raise ParameterValidationError("invalid_end_monopolies_to_trigger_end")

        tiles = end_raw.get("tiles_to_trigger_end", default_end.tiles_to_trigger_end)
        if tiles is not None:
            if isinstance(tiles, bool) or not isinstance(tiles, int) or tiles < 1:
                raise ParameterValidationError("invalid_end_tiles_to_trigger_end")
            tiles = int(tiles)

        alive = end_raw.get("alive_players_at_most", default_end.alive_players_at_most)
        if isinstance(alive, bool) or not isinstance(alive, int) or alive < 1:
            raise ParameterValidationError("invalid_end_alive_players_at_most")

        max_rounds = end_raw.get("max_rounds", runtime_raw.get("max_rounds", default_end.max_rounds))
        if max_rounds is not None:
            if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
                raise ParameterValidationError("invalid_end_max_rounds")
            max_rounds = int(max_rounds)

        max_turns = end_raw.get("max_turns", runtime_raw.get("max_turns", default_end.max_turns))
        if max_turns is not None:
            if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 1:
                raise ParameterValidationError("invalid_end_max_turns")
            max_turns = int(max_turns)

        return {
            "f_threshold": f_threshold,
            "monopolies_to_trigger_end": int(monopolies),
            "tiles_to_trigger_end": tiles,
            "alive_players_at_most": int(alive),
            "max_rounds": max_rounds,
            "max_turns": max_turns,
        }

    @staticmethod
    def _resolve_start_reward_rules(cfg: Any) -> dict[str, int]:
        rules = getattr(getattr(cfg, "rules", None), "start_reward", None)
        return {
            "points_budget": int(getattr(rules, "points_budget", 20)),
            "cash_point_cost": int(getattr(rules, "cash_point_cost", 2)),
            "shards_point_cost": int(getattr(rules, "shards_point_cost", 3)),
            "coins_point_cost": int(getattr(rules, "coins_point_cost", 3)),
            "cash_pool": int(getattr(rules, "cash_pool", 30)),
            "shards_pool": int(getattr(rules, "shards_pool", 18)),
            "coins_pool": int(getattr(rules, "coins_pool", 18)),
        }

    def _resolve_seat_limits(self, raw: dict[str, Any], default_player_count: int) -> dict[str, Any]:
        seat_limits_raw = raw.get("seat_limits")
        if seat_limits_raw is None:
            seat_limits_raw = {}
        if not isinstance(seat_limits_raw, dict):
            raise ParameterValidationError("invalid_seat_limits")

        min_seat = seat_limits_raw.get("min", 2)
        max_seat = seat_limits_raw.get("max", default_player_count)
        if not isinstance(min_seat, int) or not isinstance(max_seat, int):
            raise ParameterValidationError("invalid_seat_limits")
        if min_seat < 1 or max_seat < min_seat:
            raise ParameterValidationError("invalid_seat_limits")
        if max_seat > default_player_count:
            # Current runtime profile support. Higher values require engine/session expansion.
            raise ParameterValidationError("seat_limit_exceeds_runtime_profile")

        allowed = seat_limits_raw.get("allowed")
        if allowed is None:
            allowed = list(range(1, max_seat + 1))
        if not isinstance(allowed, list) or not allowed:
            raise ParameterValidationError("invalid_allowed_seats")
        if not all(isinstance(v, int) for v in allowed):
            raise ParameterValidationError("invalid_allowed_seats")
        allowed_sorted = sorted(set(int(v) for v in allowed))
        if allowed_sorted[0] < 1:
            raise ParameterValidationError("invalid_allowed_seats")
        if allowed_sorted[-1] > max_seat:
            raise ParameterValidationError("invalid_allowed_seats")

        return {
            "min": int(min_seat),
            "max": int(max_seat),
            "allowed": allowed_sorted,
            "default_profile_max": int(default_player_count),
        }

    @staticmethod
    def _load_default_config():
        root = Path(__file__).resolve().parents[4]
        engine_dir = root / "engine"
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        from config import DEFAULT_CONFIG

        return copy.deepcopy(DEFAULT_CONFIG)


class PublicManifestBuilder:
    """Build session-scoped public parameter manifest."""

    def __init__(self, registry: RootSourceRegistry | None = None) -> None:
        self._registry = registry or RootSourceRegistry()

    def build_public_manifest(self, params: dict[str, Any]) -> dict[str, Any]:
        fingerprints = self._registry.compute_fingerprints()
        manifest_core = {
            "manifest_version": 1,
            "version": params.get("version", "v1"),
            "participants": params.get("participants", {}),
            "board": params.get("board", {}),
            "seats": params.get("seats", {}),
            "dice": params.get("dice", {}),
            "economy": params.get("economy", {}),
            "resources": params.get("resources", {}),
            "rules": params.get("rules", {}),
            "labels": params.get("labels", {}),
            "source_fingerprints": fingerprints,
        }
        digest_source = json.dumps(manifest_core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        manifest_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        return {
            **manifest_core,
            "manifest_hash": manifest_hash,
        }
