from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class ParameterValidationError(ValueError):
    """Raised when session config cannot be resolved into safe runtime parameters."""


class RootSourceRegistry:
    """Canonical root-source registry for fingerprint generation."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parents[4]

    def list_sources(self) -> list[tuple[str, Path]]:
        gpt = self._root_dir / "GPT"
        return [
            ("ruleset", gpt / "ruleset.json"),
            ("board_layout", gpt / "board_layout.json"),
            ("characters", gpt / "characters.py"),
            ("trick_cards", gpt / "trick_cards.py"),
            ("weather_cards", gpt / "weather_cards.py"),
            ("fortune_cards", gpt / "fortune_cards.py"),
            ("config", gpt / "config.py"),
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


class GameParameterResolver:
    """Resolve session config into runtime-safe game parameter set."""

    def __init__(self, registry: RootSourceRegistry | None = None) -> None:
        self._registry = registry or RootSourceRegistry()

    def resolve(self, session_config: dict[str, Any] | None) -> dict[str, Any]:
        cfg = self._load_default_config()
        raw = dict(session_config or {})
        seat_limits = self._resolve_seat_limits(raw=raw, default_player_count=int(cfg.player_count))
        board_topology = self._resolve_board_topology(raw=raw)
        participant_defaults = self._resolve_participant_defaults(raw=raw)

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
            "runtime": {
                "seed": int(raw.get("seed", 42)),
                "policy_mode": str(raw.get("policy_mode", "")).strip() or None,
                "player_count": int(seat_limits["max"]),
            },
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
            "labels": labels,
        }

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

        timeout_ms = external_ai_raw.get("timeout_ms", 15000)
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

        headers = external_ai_raw.get("headers") or {}
        if not isinstance(headers, dict):
            raise ParameterValidationError("invalid_external_ai_headers")
        normalized_headers: dict[str, str] = {}
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ParameterValidationError("invalid_external_ai_headers")
            normalized_headers[key] = value

        return {
            "external_ai": {
                "transport": transport,
                "contract_version": contract_version,
                "timeout_ms": int(timeout_ms),
                "retry_count": int(retry_count),
                "backoff_ms": int(backoff_ms),
                "fallback_mode": fallback_mode,
                "healthcheck_path": healthcheck_path,
                "healthcheck_ttl_ms": int(healthcheck_ttl_ms),
                "endpoint": endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None,
                "required_capabilities": normalized_capabilities,
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
        gpt_dir = root / "GPT"
        if str(gpt_dir) not in sys.path:
            sys.path.insert(0, str(gpt_dir))
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
            "labels": params.get("labels", {}),
            "source_fingerprints": fingerprints,
        }
        digest_source = json.dumps(manifest_core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        manifest_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        return {
            **manifest_core,
            "manifest_hash": manifest_hash,
        }
