from __future__ import annotations

import json
import re
import subprocess
import csv
from pathlib import Path

WEATHER_ASSERT_TEMPLATE = r'getByText\(\s*["\']{name}\s*/\s*[^"\']+["\']\s*\)'


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_catalog(root: Path) -> dict:
    return json.loads((root / "packages" / "ui-domain" / "gameplay_catalog.json").read_text(encoding="utf-8"))


def _load_named_card_values(csv_path: Path) -> set[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        values: set[str] = set()
        for row in reader:
            name = " ".join((row.get("이름") or "").split())
            if name:
                values.add(name)
        return values


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
    }:
        return False
    return rel.startswith("apps/web/src/domain/") or rel.startswith("apps/server/src/domain/")


def _is_runtime_logic_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return rel in {
        "engine/ai_policy.py",
        "engine/effect_handlers.py",
        "engine/engine.py",
        "engine/policy_groups.py",
        "engine/policy_mark_utils.py",
        "engine/policy/environment_traits.py",
        "engine/policy/evaluator/character_scoring.py",
        "engine/policy/profile/presets.py",
        "engine/policy/decision/purchase.py",
    }


ALLOWED_LITERAL_EXCEPTIONS: dict[str, set[str]] = {
    "engine/policy/environment_traits.py": {
        "자원 순환",
        "자원 재활용",
        "모두의 순환",
        "모두의 재활용",
    },
    "engine/engine.py": {"어사"},
}


def _character_literals(catalog: dict) -> set[str]:
    literals: set[str] = set()
    for slot in catalog["character_slots"]:
        for face in slot["faces"]:
            literals.add(str(face["name"]))
            for alias in face.get("aliases", []):
                literals.add(str(alias))
    return literals


def _weather_literals(root: Path) -> set[str]:
    return _load_named_card_values(root / "engine" / "weather.csv")


def _fortune_literals(root: Path) -> set[str]:
    return _load_named_card_values(root / "engine" / "fortune.csv")


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
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in ALLOWED_LITERAL_EXCEPTIONS.get(rel, set()):
                continue
            if literal in text:
                failures.append(f"gameplay name literal '{literal}' must not appear in domain logic file: {rel}")
                break
    return failures


def _check_runtime_weather_fortune_literals(paths: list[Path], root: Path) -> list[str]:
    failures: list[str] = []
    literals = _weather_literals(root) | _fortune_literals(root)
    for path in paths:
        if not path.is_file() or not _is_runtime_logic_file(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in ALLOWED_LITERAL_EXCEPTIONS.get(rel, set()):
                continue
            if literal in text:
                failures.append(f"weather/fortune literal '{literal}' must not appear in runtime logic file: {rel}")
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
    failures = (
        _check_domain_literals(tracked, root, catalog)
        + _check_runtime_weather_fortune_literals(tracked, root)
        + _check_brittle_weather_assertions(tracked, root, catalog)
    )
    if failures:
        print("FAIL: gameplay literal gate violations detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("OK: gameplay literal gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
