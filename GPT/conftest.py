from __future__ import annotations

import json
import random
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from test_import_bootstrap import activate_test_root


THIS_DIR = Path(__file__).resolve().parent
SIBLING_DIR = (THIS_DIR.parent / "CLAUDE").resolve()


def _purge_sibling_modules() -> None:
    activate_test_root(THIS_DIR, SIBLING_DIR)


_purge_sibling_modules()


def pytest_collect_file(file_path, parent):  # type: ignore[no-untyped-def]
    _purge_sibling_modules()
    return None


def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    _purge_sibling_modules()


def _wait_until_reachable(url: str, attempts: int = 40, delay_seconds: float = 0.1) -> None:
    for _ in range(attempts):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(delay_seconds)
    raise RuntimeError(f"Timed out waiting for server: {url}")


@pytest.fixture(scope="module")
def port(request, free_tcp_port_factory: pytest.TempPathFactory) -> int:
    module_name = request.module.__name__
    port = free_tcp_port_factory()

    if module_name.endswith("test_human_play"):
        from viewer.prompt_server import HumanPlayServer

        server = HumanPlayServer(seed=99, port=port, turn_delay=0.0, human_seat=0, human_seats=None)
        health_path = "/status"
    elif module_name.endswith("test_live_server"):
        from viewer.live_server import LiveGameServer

        server = LiveGameServer(seed=42, port=port, turn_delay=0.0)
        health_path = "/status"
    else:
        raise RuntimeError(f"Unsupported port fixture consumer: {module_name}")

    thread = threading.Thread(target=server.start, daemon=True, name=f"pytest-server:{module_name}")
    thread.start()
    _wait_until_reachable(f"http://127.0.0.1:{port}{health_path}")
    try:
        yield port
    finally:
        http_server = getattr(server, "_http_server", None)
        if http_server is not None:
            http_server.shutdown()
        thread.join(timeout=2.0)


def _build_replay_events(seed: int = 42) -> list[dict]:
    from ai_policy import HeuristicPolicy
    from config import DEFAULT_CONFIG
    from engine import GameEngine
    from viewer.stream import VisEventStream

    stream = VisEventStream()
    policy = HeuristicPolicy(
        character_policy_mode="heuristic_v1",
        lap_policy_mode="heuristic_v1",
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return json.loads(json.dumps(stream.to_list(), ensure_ascii=False))


@pytest.fixture(scope="module")
def events() -> list[dict]:
    return _build_replay_events()


@pytest.fixture(scope="module")
def _events(events: list[dict]) -> list[dict]:
    return events
