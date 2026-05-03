from __future__ import annotations

from pathlib import Path


REQUIRED_FILES = [
    "docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md",
    "docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md",
    "docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md",
]

REQUIRED_REFERENCES = {
    "docs/current/planning/PLAN_STATUS_INDEX.md": [
        "docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md",
        "docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md",
    ],
    "docs/current/backend/README.md": [
        "docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md",
        "docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md",
    ],
}

REQUIRED_SNIPPETS = {
    "docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md": [
        "CP-949",
        "UTF-8",
        "DecisionRequest -> DecisionResponse",
        "작업 원칙 - 소규모/대규모 작업에 관계 없이 어떤 일을 했는지 요약하여 작업 일지 문서에 남긴다.",
        "작업 원칙 - 로직 등 복잡한 변경은 계획 문서를 먼저 작성한다.",
    ],
    "docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md": [
        "P0",
        "Always-Check Order",
    ],
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_required_files(root: Path, failures: list[str]) -> None:
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file():
            failures.append(f"missing required file: {rel}")


def _check_required_references(root: Path, failures: list[str]) -> None:
    for rel, expected_refs in REQUIRED_REFERENCES.items():
        path = root / rel
        if not path.is_file():
            failures.append(f"missing reference host file: {rel}")
            continue
        content = _read_utf8(path)
        for ref in expected_refs:
            if ref not in content:
                failures.append(f"missing reference '{ref}' in {rel}")


def _check_required_snippets(root: Path, failures: list[str]) -> None:
    for rel, snippets in REQUIRED_SNIPPETS.items():
        path = root / rel
        if not path.is_file():
            failures.append(f"missing snippet host file: {rel}")
            continue
        content = _read_utf8(path)
        for snippet in snippets:
            if snippet not in content:
                failures.append(f"missing policy snippet '{snippet}' in {rel}")


def main() -> int:
    root = _project_root()
    failures: list[str] = []

    _check_required_files(root, failures)
    _check_required_references(root, failures)
    _check_required_snippets(root, failures)

    if failures:
        print("FAIL: plan/policy gate violations detected:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("OK: plan/policy mandatory docs and references are fixed and valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
