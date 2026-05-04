from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _snapshot_path(root: Path) -> Path:
    return root / "tools" / "parameter_manifest_snapshot.json"


def _build_snapshot_payload() -> dict:
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from apps.server.src.services.parameter_service import GameParameterResolver, PublicManifestBuilder

    resolver = GameParameterResolver()
    builder = PublicManifestBuilder()
    resolved = resolver.resolve({"seed": 42})
    manifest = builder.build_public_manifest(resolved)
    return {
        "manifest_version": manifest.get("manifest_version"),
        "manifest_hash": manifest.get("manifest_hash"),
        "source_fingerprints": manifest.get("source_fingerprints", {}),
        "board_tile_count": manifest.get("board", {}).get("tile_count"),
        "seat_limits": manifest.get("seats", {}),
        "dice_values": manifest.get("dice", {}).get("values", []),
    }


def _write_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_snapshot(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_snapshot(path: Path, payload: dict) -> int:
    try:
        current = _load_snapshot(path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2
    if current == payload:
        print("OK: parameter manifest snapshot is up to date.")
        return 0
    print("FAIL: parameter manifest snapshot is stale.")
    print(f"snapshot: {path}")
    print(f"previous manifest_hash: {current.get('manifest_hash')}")
    print(f"new manifest_hash: {payload.get('manifest_hash')}")
    old_fp = current.get("source_fingerprints", {})
    new_fp = payload.get("source_fingerprints", {})
    changed = sorted(set(old_fp.keys()) | set(new_fp.keys()))
    for key in changed:
        if old_fp.get(key) != new_fp.get(key):
            print(f"  - {key}: {old_fp.get(key)} -> {new_fp.get(key)}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Parameter manifest stale-artifact gate helper")
    parser.add_argument("--write", action="store_true", help="Write/update snapshot file.")
    parser.add_argument("--check", action="store_true", help="Check snapshot and fail if stale.")
    args = parser.parse_args()

    root = _project_root()
    snapshot_file = _snapshot_path(root)
    payload = _build_snapshot_payload()

    if args.write:
        _write_snapshot(snapshot_file, payload)
        print(f"Wrote snapshot: {snapshot_file}")
        return 0
    if args.check:
        return _check_snapshot(snapshot_file, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
