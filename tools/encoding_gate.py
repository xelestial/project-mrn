from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TEXT_SUFFIX_ALLOWLIST = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".css",
    ".html",
    ".sh",
    ".bat",
    ".ps1",
    ".csv",
    ".sql",
    ".xml",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _tracked_files(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[Path] = []
    for rel in proc.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        path = root / rel
        if path.is_file():
            files.append(path)
    return files


def _is_text_candidate(path: Path) -> bool:
    name = path.name.lower()
    if name in {".gitignore", ".gitattributes", ".editorconfig"}:
        return True
    return path.suffix.lower() in TEXT_SUFFIX_ALLOWLIST


def _check_utf8(paths: list[Path], root: Path) -> tuple[list[str], list[str]]:
    invalid: list[str] = []
    bom: list[str] = []
    for path in paths:
        if not _is_text_candidate(path):
            continue
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            bom.append(path.relative_to(root).as_posix())
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            invalid.append(path.relative_to(root).as_posix())
    return invalid, bom


def main() -> int:
    root = _project_root()
    tracked = _tracked_files(root)
    invalid, bom = _check_utf8(tracked, root)

    if not invalid and not bom:
        print("OK: all tracked text files are valid UTF-8 without BOM.")
        return 0

    if invalid:
        print("FAIL: non-UTF-8 text files detected (cp949/euc-kr etc. not allowed):")
        for rel in invalid:
            print(f"  - {rel}")

    if bom:
        print("FAIL: UTF-8 BOM files detected (use UTF-8 without BOM):")
        for rel in bom:
            print(f"  - {rel}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
