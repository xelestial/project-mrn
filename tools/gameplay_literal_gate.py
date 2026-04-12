from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

WEATHER_ASSERT_TEMPLATE = r'getByText\(\s*["\']{name}\s*/\s*[^"\']+["\']\s*\)'


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_catalog(root: Path) -> dict:
    return json.loads((root / "packages" / "ui-domain" / "gameplay_catalog.json").read_text(encoding="utf-8"))


def _tracked_files(root: Path) -> list[Path]:
    proc = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    return [root / rel for rel in proc.stdout.splitlines() if rel.strip()]


def _is_domain_logic_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if rel.endswith(".spec.ts") or rel.endswith(".spec.tsx") or rel.endswith("_test.py") or "/tests/" in rel:
        return False
    if rel in {
        "apps/web/src/domain/catalogs/gameplayCatalog.ts",
        "apps/web/src/domain/characters/prioritySlots.ts",
        "apps/server/src/domain/gameplay_catalog.py",
        "apps/server/src/domain/view_state/player_selector.py",
        "GPT/policy_groups.py",
        "GPT/policy_mark_utils.py",
        "GPT/policy/environment_traits.py",
        "GPT/policy/decision/purchase.py",
    }:
        return False
    return rel.startswith("apps/web/src/domain/") or rel.startswith("apps/server/src/domain/")


def _is_runtime_logic_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return rel in {
        "GPT/policy_groups.py",
        "GPT/policy_mark_utils.py",
        "GPT/policy/environment_traits.py",
        "GPT/policy/decision/purchase.py",
    }


def _character_literals(catalog: dict) -> set[str]:
    literals: set[str] = set()
    for slot in catalog["character_slots"]:
        for face in slot["faces"]:
            literals.add(str(face["name"]))
            for alias in face.get("aliases", []):
                literals.add(str(alias))
    return literals


def _weather_join_patterns(catalog: dict) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for weather in catalog["weather_cards"]:
        name = re.escape(str(weather["name"]))
        patterns.append(re.compile(WEATHER_ASSERT_TEMPLATE.format(name=name)))
    return patterns


def _check_domain_literals(paths: list[Path], root: Path, catalog: dict) -> list[str]:
    failures: list[str] = []
    literals = _character_literals(catalog)
    for path in paths:
        if not path.is_file() or not (_is_domain_logic_file(path, root) or _is_runtime_logic_file(path, root)):
            continue
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in text:
                failures.append(f"gameplay name literal '{literal}' must not appear in domain logic file: {path.relative_to(root).as_posix()}")
                break
    return failures


def _check_brittle_weather_assertions(paths: list[Path], root: Path, catalog: dict) -> list[str]:
    failures: list[str] = []
    patterns = _weather_join_patterns(catalog)
    for path in paths:
        rel = path.relative_to(root).as_posix()
        if not rel.startswith("apps/web/e2e/") or path.suffix != ".ts":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern.search(text):
                failures.append(f"brittle combined weather text assertion found in e2e file: {rel}")
                break
    return failures


def main() -> int:
    root = _project_root()
    tracked = _tracked_files(root)
    catalog = _load_catalog(root)
    failures = _check_domain_literals(tracked, root, catalog) + _check_brittle_weather_assertions(tracked, root, catalog)
    if failures:
        print("FAIL: gameplay literal gate violations detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("OK: gameplay literal gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
