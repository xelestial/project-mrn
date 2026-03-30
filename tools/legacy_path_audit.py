from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_PATTERNS = ("GPT/", "CLAUDE/", "frontend/")
DEFAULT_ROOTS = ("apps", "packages", "PLAN", "tools")
DEFAULT_IGNORE_FILES = ("tools/legacy_path_audit.py",)


def scan(root: Path, roots: list[str], patterns: list[str], ignore_files: list[str]) -> dict:
    report: dict[str, list[dict]] = {pattern: [] for pattern in patterns}
    ignored = {item.replace("\\", "/") for item in ignore_files}
    for root_name in roots:
        base = root / root_name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel_path = str(path.relative_to(root)).replace("\\", "/")
            if rel_path in ignored:
                continue
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            lines = text.splitlines()
            for idx, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if pattern in line:
                        report[pattern].append(
                            {
                                "file": rel_path,
                                "line": idx,
                                "text": line.strip(),
                            }
                        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy path references in active code/docs.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--roots", nargs="*", default=list(DEFAULT_ROOTS))
    parser.add_argument("--patterns", nargs="*", default=list(DEFAULT_PATTERNS))
    parser.add_argument("--ignore-files", nargs="*", default=list(DEFAULT_IGNORE_FILES))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when matches exist")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = scan(
        root=root,
        roots=list(args.roots),
        patterns=list(args.patterns),
        ignore_files=list(args.ignore_files),
    )
    counts = {pattern: len(items) for pattern, items in report.items()}

    payload = json.dumps({"counts": counts, "matches": report}, ensure_ascii=False, indent=2)
    try:
        print(payload)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(payload.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")

    if args.strict and any(counts.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
