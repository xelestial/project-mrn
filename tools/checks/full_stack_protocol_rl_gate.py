from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine"
WEB_DIR = ROOT / "apps" / "web"
VITE_NODE = WEB_DIR / "node_modules" / ".bin" / "vite-node"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from rl.replay import iter_replay_rows  # noqa: E402
from rl.train_policy import train_behavior_clone  # noqa: E402


VALID_RECONNECT_SCENARIOS = {
    "after_start",
    "after_first_commit",
    "after_first_decision",
    "round_boundary",
    "turn_boundary",
}
DEFAULT_RECONNECT_SCENARIOS = tuple(sorted(VALID_RECONNECT_SCENARIOS))

PROFILES: dict[str, dict[str, int]] = {
    "smoke": {
        "baseline_seed_count": 1,
        "candidate_seed_count": 1,
        "epochs": 1,
        "hidden_size": 16,
    },
    "local": {
        "baseline_seed_count": 5,
        "candidate_seed_count": 5,
        "epochs": 4,
        "hidden_size": 64,
    },
    "full": {
        "baseline_seed_count": 20,
        "candidate_seed_count": 20,
        "epochs": 8,
        "hidden_size": 64,
    },
}

PROFILE_DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "smoke": {
        "rules": {
            "end": {
                "f_threshold": 4,
                "monopolies_to_trigger_end": 1,
                "tiles_to_trigger_end": 4,
                "alive_players_at_most": 1,
            }
        }
    }
}


def run_full_stack_protocol_rl_gate(
    *,
    output_dir: str | Path,
    base_url: str,
    profile: str,
    seed: int,
    baseline_seed_count: int | None = None,
    candidate_seed_count: int | None = None,
    timeout_ms: int = 1_800_000,
    idle_timeout_ms: int = 120_000,
    policy_http_timeout_ms: int = 2_000,
    progress_interval_ms: int = 30_000,
    cpu_diagnostic_idle_ms: int = 30_000,
    cpu_low_load_percent: float = 10.0,
    epochs: int | None = None,
    hidden_size: int | None = None,
    config: Mapping[str, Any] | None = None,
    reconnect_scenarios: Iterable[str] | None = DEFAULT_RECONNECT_SCENARIOS,
    max_avg_rank_delta: float = 1.0,
    max_bankruptcy_rate_delta: float = 0.25,
    min_avg_reward_delta: float = -1.0,
) -> dict[str, Any]:
    config_for_profile = dict(PROFILES[profile])
    effective_config = resolve_profile_config(profile, config)
    baseline_count = int(baseline_seed_count or config_for_profile["baseline_seed_count"])
    candidate_count = int(candidate_seed_count or config_for_profile["candidate_seed_count"])
    train_epochs = int(epochs or config_for_profile["epochs"])
    train_hidden_size = int(hidden_size or config_for_profile["hidden_size"])
    effective_reconnect_scenarios = normalize_reconnect_scenarios(reconnect_scenarios)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    baseline_runs: list[dict[str, Any]] = []
    baseline_replays: list[Path] = []
    for index in range(baseline_count):
        run_seed = int(seed) + index
        run_dir = out / "baseline" / f"seed_{run_seed}"
        summary = run_protocol_gate_once(
            run_dir=run_dir,
            base_url=base_url,
            seed=run_seed,
            policy="baseline",
            timeout_ms=timeout_ms,
            idle_timeout_ms=idle_timeout_ms,
            policy_http_timeout_ms=policy_http_timeout_ms,
            progress_interval_ms=progress_interval_ms,
            cpu_diagnostic_idle_ms=cpu_diagnostic_idle_ms,
            cpu_low_load_percent=cpu_low_load_percent,
            config=effective_config,
            reconnect_scenarios=effective_reconnect_scenarios,
        )
        baseline_runs.append(summary)
        baseline_replays.append(run_dir / "rl_replay.jsonl")

    train_dir = out / "train"
    train_replay = train_dir / "rl_replay.jsonl"
    train_row_count = concatenate_replay_files(baseline_replays, train_replay)
    model_dir = out / "model"
    model_summary = train_behavior_clone(
        replay_path=train_replay,
        output_dir=model_dir,
        seed=seed,
        epochs=train_epochs,
        hidden_size=train_hidden_size,
    )

    candidate_runs: list[dict[str, Any]] = []
    candidate_replays: list[Path] = []
    baseline_stable = all(bool(summary.get("ok")) for summary in baseline_runs)
    if baseline_stable and train_row_count > 0 and int(model_summary.get("train_examples") or 0) > 0:
        server_dir = out / "policy_server"
        with start_protocol_policy_server(model_dir=model_dir, output_dir=server_dir) as policy_url:
            for index in range(candidate_count):
                run_seed = int(seed) + 10_000 + index
                run_dir = out / "candidate" / f"seed_{run_seed}"
                summary = run_protocol_gate_once(
                    run_dir=run_dir,
                    base_url=base_url,
                    seed=run_seed,
                    policy="http",
                    policy_http_url=policy_url,
                    timeout_ms=timeout_ms,
                    idle_timeout_ms=idle_timeout_ms,
                    policy_http_timeout_ms=policy_http_timeout_ms,
                    progress_interval_ms=progress_interval_ms,
                    cpu_diagnostic_idle_ms=cpu_diagnostic_idle_ms,
                    cpu_low_load_percent=cpu_low_load_percent,
                    config=effective_config,
                    reconnect_scenarios=effective_reconnect_scenarios,
                )
                candidate_runs.append(summary)
                candidate_replays.append(run_dir / "rl_replay.jsonl")

    baseline_metrics = compute_replay_metrics(baseline_replays)
    candidate_metrics = compute_replay_metrics(candidate_replays)
    acceptance = evaluate_full_stack_acceptance(
        baseline_summaries=baseline_runs,
        candidate_summaries=candidate_runs,
        train_row_count=train_row_count,
        model_summary=model_summary,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        max_avg_rank_delta=max_avg_rank_delta,
        max_bankruptcy_rate_delta=max_bankruptcy_rate_delta,
        min_avg_reward_delta=min_avg_reward_delta,
    )
    summary = {
        "version": 1,
        "profile": profile,
        "base_url": base_url,
        "output_dir": str(out),
        "seed": seed,
        "config": effective_config,
        "reconnect_scenarios": effective_reconnect_scenarios,
        "baseline": {
            "seed_count": baseline_count,
            "runs": baseline_runs,
            "metrics": baseline_metrics,
        },
        "train": {
            "replay_path": str(train_replay),
            "row_count": train_row_count,
            "model_dir": str(model_dir),
            "model": model_summary,
        },
        "candidate": {
            "seed_count": candidate_count,
            "runs": candidate_runs,
            "metrics": candidate_metrics,
        },
        "acceptance": acceptance,
    }
    summary_path = out / "pipeline_summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def resolve_profile_config(profile: str, config: Mapping[str, Any] | None) -> dict[str, Any]:
    if config is not None:
        return dict(config)
    return json.loads(json.dumps(PROFILE_DEFAULT_CONFIGS.get(profile, {})))


def normalize_reconnect_scenarios(scenarios: Iterable[str] | None) -> list[str]:
    if scenarios is None:
        return []
    normalized: list[str] = []
    invalid: list[str] = []
    for raw in scenarios:
        value = str(raw).strip()
        if not value:
            continue
        if value not in VALID_RECONNECT_SCENARIOS:
            invalid.append(value)
            continue
        if value not in normalized:
            normalized.append(value)
    if invalid:
        valid = ", ".join(sorted(VALID_RECONNECT_SCENARIOS))
        raise ValueError(f"invalid reconnect scenario(s): {', '.join(invalid)}. valid values: {valid}")
    return normalized


def run_protocol_gate_once(
    *,
    run_dir: Path,
    base_url: str,
    seed: int,
    policy: str,
    timeout_ms: int,
    idle_timeout_ms: int,
    policy_http_timeout_ms: int,
    progress_interval_ms: int,
    cpu_diagnostic_idle_ms: int,
    cpu_low_load_percent: float,
    policy_http_url: str | None = None,
    config: Mapping[str, Any] | None = None,
    reconnect_scenarios: Iterable[str] | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = (run_dir / "protocol_trace.jsonl").resolve()
    replay_path = (run_dir / "rl_replay.jsonl").resolve()
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    summary_path = run_dir / "summary.json"
    command = protocol_gate_command(
        base_url=base_url,
        seed=seed,
        policy=policy,
        trace_path=trace_path,
        replay_path=replay_path,
        timeout_ms=timeout_ms,
        idle_timeout_ms=idle_timeout_ms,
        policy_http_timeout_ms=policy_http_timeout_ms,
        progress_interval_ms=progress_interval_ms,
        cpu_diagnostic_idle_ms=cpu_diagnostic_idle_ms,
        cpu_low_load_percent=cpu_low_load_percent,
        policy_http_url=policy_http_url,
        config=config,
        reconnect_scenarios=reconnect_scenarios,
    )
    completed = subprocess.run(
        command,
        cwd=WEB_DIR,
        text=True,
        capture_output=True,
        timeout=max(60, int(timeout_ms / 1000) + 60),
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    try:
        summary = parse_protocol_gate_summary(completed.stdout)
    except ValueError:
        summary = {
            "ok": False,
            "profile": "live",
            "policy_mode": policy,
            "seed": seed,
            "runtime_status": None,
            "failures": ["protocol gate did not emit parseable JSON summary"],
        }
    summary["seed"] = seed
    summary["process_returncode"] = completed.returncode
    summary["trace_path"] = str(trace_path)
    summary["replay_path"] = str(replay_path)
    summary["stdout_path"] = str(stdout_path)
    summary["stderr_path"] = str(stderr_path)
    summary["reconnect_scenarios"] = normalize_reconnect_scenarios(reconnect_scenarios)
    if completed.returncode != 0 and bool(summary.get("ok")):
        summary["ok"] = False
        summary.setdefault("failures", []).append(f"protocol gate exited with {completed.returncode}")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def protocol_gate_command(
    *,
    base_url: str,
    seed: int,
    policy: str,
    trace_path: Path,
    replay_path: Path,
    timeout_ms: int,
    idle_timeout_ms: int,
    policy_http_timeout_ms: int,
    progress_interval_ms: int,
    cpu_diagnostic_idle_ms: int,
    cpu_low_load_percent: float,
    policy_http_url: str | None = None,
    config: Mapping[str, Any] | None = None,
    reconnect_scenarios: Iterable[str] | None = None,
) -> list[str]:
    if VITE_NODE.exists():
        command = [str(VITE_NODE), "src/headless/runFullStackProtocolGate.ts"]
    else:
        command = ["npm", "run", "rl:protocol-gate", "--"]
    command.extend(
        [
            "--base-url",
            base_url,
            "--profile",
            "live",
            "--seed",
            str(seed),
            "--timeout-ms",
            str(timeout_ms),
            "--idle-timeout-ms",
            str(idle_timeout_ms),
            "--out",
            str(trace_path),
            "--replay-out",
            str(replay_path),
            "--progress-interval-ms",
            str(progress_interval_ms),
            "--cpu-diagnostic-idle-ms",
            str(cpu_diagnostic_idle_ms),
            "--cpu-low-load-percent",
            str(cpu_low_load_percent),
            "--raw-prompt-fallback-delay-ms",
            "off",
            "--policy",
            policy,
        ]
    )
    if config:
        command.extend(["--config-json", json.dumps(dict(config), ensure_ascii=False, sort_keys=True)])
    normalized_reconnect_scenarios = normalize_reconnect_scenarios(reconnect_scenarios)
    if normalized_reconnect_scenarios:
        command.extend(["--reconnect", ",".join(normalized_reconnect_scenarios)])
    if policy == "http":
        if not policy_http_url:
            raise ValueError("HTTP policy run requires policy_http_url")
        command.extend(
            [
                "--policy-http-url",
                policy_http_url,
                "--policy-http-timeout-ms",
                str(policy_http_timeout_ms),
            ]
        )
    return command


def parse_protocol_gate_summary(stdout: str) -> dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        raise ValueError("empty protocol gate stdout")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(stripped[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    for line in reversed(stripped.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("protocol gate stdout did not contain a JSON object")


def concatenate_replay_files(paths: Iterable[Path], target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as writer:
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as reader:
                for line in reader:
                    if not line.strip():
                        continue
                    writer.write(line if line.endswith("\n") else f"{line}\n")
                    count += 1
    return count


def compute_replay_metrics(paths: Iterable[Path]) -> dict[str, Any]:
    row_count = 0
    reward_sum = 0.0
    final_by_player: dict[tuple[str, int], dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        for row in iter_replay_rows(path):
            row_count += 1
            reward = row.get("reward") if isinstance(row.get("reward"), dict) else {}
            reward_sum += _float_or_zero(reward.get("total"))
            outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
            player_id = _int_or_none(row.get("player_id"))
            game_id = str(row.get("game_id") or path.stem)
            if player_id is None:
                continue
            final_rank = _number_or_none(outcome.get("final_rank"))
            final_summary = outcome.get("final_player_summary") if isinstance(outcome.get("final_player_summary"), dict) else None
            if final_rank is not None or final_summary is not None:
                final_by_player[(game_id, player_id)] = {
                    "rank": final_rank,
                    "summary": final_summary or {},
                }
    ranks = [float(item["rank"]) for item in final_by_player.values() if item["rank"] is not None]
    bankruptcies = [
        _is_bankrupt(item["summary"])
        for item in final_by_player.values()
        if isinstance(item.get("summary"), dict) and item["summary"]
    ]
    return {
        "rows": row_count,
        "decisions": row_count,
        "players": len(final_by_player),
        "average_reward": round(reward_sum / row_count, 6) if row_count else None,
        "average_final_rank": round(sum(ranks) / len(ranks), 6) if ranks else None,
        "bankruptcy_rate": round(sum(1 for item in bankruptcies if item) / len(bankruptcies), 6) if bankruptcies else None,
    }


def evaluate_full_stack_acceptance(
    *,
    baseline_summaries: list[Mapping[str, Any]],
    candidate_summaries: list[Mapping[str, Any]],
    train_row_count: int,
    model_summary: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
    max_avg_rank_delta: float,
    max_bankruptcy_rate_delta: float,
    min_avg_reward_delta: float,
) -> dict[str, Any]:
    baseline_ok = bool(baseline_summaries) and all(bool(summary.get("ok")) for summary in baseline_summaries)
    candidate_ok = bool(candidate_summaries) and all(bool(summary.get("ok")) for summary in candidate_summaries)
    train_rows_ok = int(train_row_count) > 0
    model_examples_ok = int(model_summary.get("train_examples") or 0) > 0
    avg_rank_delta = _metric_delta(candidate_metrics.get("average_final_rank"), baseline_metrics.get("average_final_rank"))
    bankruptcy_delta = _metric_delta(candidate_metrics.get("bankruptcy_rate"), baseline_metrics.get("bankruptcy_rate"))
    avg_reward_delta = _metric_delta(candidate_metrics.get("average_reward"), baseline_metrics.get("average_reward"))
    checks = {
        "baseline_protocol_ok": baseline_ok,
        "candidate_protocol_ok": candidate_ok,
        "train_replay_nonempty": train_rows_ok,
        "model_train_examples_nonempty": model_examples_ok,
        "candidate_average_rank_not_regressed": avg_rank_delta is not None and avg_rank_delta <= max_avg_rank_delta,
        "candidate_bankruptcy_not_regressed": bankruptcy_delta is not None and bankruptcy_delta <= max_bankruptcy_rate_delta,
        "candidate_average_reward_not_regressed": avg_reward_delta is not None and avg_reward_delta >= min_avg_reward_delta,
    }
    stable = bool(checks["baseline_protocol_ok"] and checks["candidate_protocol_ok"])
    accepted = stable and all(checks.values())
    return {
        "accepted": accepted,
        "stable": stable,
        "checks": checks,
        "deltas": {
            "average_final_rank": avg_rank_delta,
            "bankruptcy_rate": bankruptcy_delta,
            "average_reward": avg_reward_delta,
        },
        "thresholds": {
            "max_avg_rank_delta": max_avg_rank_delta,
            "max_bankruptcy_rate_delta": max_bankruptcy_rate_delta,
            "min_avg_reward_delta": min_avg_reward_delta,
        },
    }


class start_protocol_policy_server:
    def __init__(
        self,
        *,
        model_dir: str | Path,
        output_dir: str | Path,
        host: str = "127.0.0.1",
        startup_timeout: float = 120.0,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.output_dir = Path(output_dir)
        self.host = host
        self.startup_timeout = startup_timeout
        self.port = find_free_port(host)
        self.endpoint = f"http://{host}:{self.port}/decide"
        self.process: subprocess.Popen[str] | None = None
        self.stdout_handle: Any = None
        self.stderr_handle: Any = None

    def __enter__(self) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stdout_handle = (self.output_dir / "stdout.log").open("w", encoding="utf-8")
        self.stderr_handle = (self.output_dir / "stderr.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = _prepend_pythonpath(str(ENGINE), env.get("PYTHONPATH"))
        self.process = subprocess.Popen(
            [
                venv_python(),
                "-m",
                "rl.protocol_policy_server",
                "--model-dir",
                str(self.model_dir),
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=self.stdout_handle,
            stderr=self.stderr_handle,
        )
        try:
            wait_for_http_health(f"http://{self.host}:{self.port}/health", self.process, timeout=self.startup_timeout)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.endpoint

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.stdout_handle is not None:
            self.stdout_handle.close()
        if self.stderr_handle is not None:
            self.stderr_handle.close()


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def wait_for_http_health(url: str, process: subprocess.Popen[str], timeout: float = 30.0) -> None:
    started = time.time()
    last_error: Exception | None = None
    while time.time() - started < timeout:
        if process.poll() is not None:
            raise RuntimeError(f"protocol policy server exited early with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"protocol policy server did not become healthy: {last_error!r}")


def venv_python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _prepend_pythonpath(path: str, current: str | None) -> str:
    if not current:
        return path
    parts = current.split(os.pathsep)
    return current if path in parts else os.pathsep.join([path, current])


def _metric_delta(candidate: Any, baseline: Any) -> float | None:
    candidate_number = _number_or_none(candidate)
    baseline_number = _number_or_none(baseline)
    if candidate_number is None or baseline_number is None:
        return None
    return round(candidate_number - baseline_number, 6)


def _is_bankrupt(summary: Mapping[str, Any]) -> bool:
    alive = summary.get("alive")
    if alive is False:
        return True
    cash = _number_or_none(summary.get("cash"))
    return cash is not None and cash <= 0


def _float_or_zero(value: Any) -> float:
    number = _number_or_none(value)
    return float(number) if number is not None else 0.0


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_json_object(raw: str, flag: str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag} must be a JSON object")
    return parsed


def parse_reconnect_arg(raw: str | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_RECONNECT_SCENARIOS)
    if raw.strip().lower() in {"", "off", "none", "false", "0"}:
        return []
    return normalize_reconnect_scenarios(raw.split(","))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full-stack REST/WebSocket RL protocol learning gate.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:9091")
    parser.add_argument("--output-dir")
    parser.add_argument("--seed", type=int, default=20260508)
    parser.add_argument("--baseline-seed-count", type=int)
    parser.add_argument("--candidate-seed-count", type=int)
    parser.add_argument("--timeout-ms", type=int, default=1_800_000)
    parser.add_argument("--idle-timeout-ms", type=int, default=120_000)
    parser.add_argument("--policy-http-timeout-ms", type=int, default=2_000)
    parser.add_argument("--progress-interval-ms", type=int, default=30_000)
    parser.add_argument("--cpu-diagnostic-idle-ms", type=int, default=30_000)
    parser.add_argument("--cpu-low-load-percent", type=float, default=10.0)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--hidden-size", type=int)
    parser.add_argument("--config-json")
    parser.add_argument(
        "--reconnect",
        default=",".join(DEFAULT_RECONNECT_SCENARIOS),
        help="Comma-separated WebSocket reconnect scenarios to force during each protocol run, or 'off'.",
    )
    parser.add_argument("--max-avg-rank-delta", type=float, default=1.0)
    parser.add_argument("--max-bankruptcy-rate-delta", type=float, default=0.25)
    parser.add_argument("--min-avg-reward-delta", type=float, default=-1.0)
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "tmp" / "rl" / "full-stack-protocol" / args.profile
    summary = run_full_stack_protocol_rl_gate(
        output_dir=output_dir,
        base_url=args.base_url,
        profile=args.profile,
        seed=args.seed,
        baseline_seed_count=args.baseline_seed_count,
        candidate_seed_count=args.candidate_seed_count,
        timeout_ms=args.timeout_ms,
        idle_timeout_ms=args.idle_timeout_ms,
        policy_http_timeout_ms=args.policy_http_timeout_ms,
        progress_interval_ms=args.progress_interval_ms,
        cpu_diagnostic_idle_ms=args.cpu_diagnostic_idle_ms,
        cpu_low_load_percent=args.cpu_low_load_percent,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
        config=parse_json_object(args.config_json, "--config-json") if args.config_json else None,
        reconnect_scenarios=parse_reconnect_arg(args.reconnect),
        max_avg_rank_delta=args.max_avg_rank_delta,
        max_bankruptcy_rate_delta=args.max_bankruptcy_rate_delta,
        min_avg_reward_delta=args.min_avg_reward_delta,
    )
    acceptance = summary["acceptance"]
    result = {
        "accepted": acceptance["accepted"],
        "stable": acceptance["stable"],
        "profile": args.profile,
        "output_dir": summary["output_dir"],
        "summary_path": summary["summary_path"],
        "checks": acceptance["checks"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.profile == "smoke":
        return 0 if acceptance["stable"] and summary["train"]["row_count"] > 0 else 1
    return 0 if acceptance["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
