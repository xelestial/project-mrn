from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from config import BoardConfig, BoardLayoutMetadata, CellKind, TileMetadata


KIND_NAME_MAP = {
    "F1": CellKind.F1,
    "F2": CellKind.F2,
    "S": CellKind.S,
    "T2": CellKind.T2,
    "T3": CellKind.T3,
    "MALICIOUS": CellKind.MALICIOUS,
}


class BoardLayoutLoadError(ValueError):
    pass


def _parse_kind(raw: str) -> CellKind:
    try:
        return KIND_NAME_MAP[raw.strip().upper()]
    except KeyError as exc:
        raise BoardLayoutLoadError(f"Unsupported tile kind: {raw}") from exc


def _parse_optional_int(value) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)


def _normalize_tile_row(row: dict) -> TileMetadata:
    return TileMetadata(
        index=int(row["index"]),
        kind=_parse_kind(str(row["kind"])),
        block_id=int(row.get("block_id", -1)),
        zone_color=(None if row.get("zone_color") in (None, "", "null") else str(row.get("zone_color"))),
        purchase_cost=_parse_optional_int(row.get("purchase_cost")),
        rent_cost=_parse_optional_int(row.get("rent_cost")),
        economy_profile=(None if row.get('economy_profile') in (None, '', 'null') else str(row.get('economy_profile'))),
    )


def _normalize_layout_metadata(raw: dict | None) -> BoardLayoutMetadata:
    return BoardLayoutMetadata.from_external_dict(raw)


def build_board_config_from_rows(tile_rows: Iterable[dict], *, layout_metadata: dict | None = None) -> BoardConfig:
    tiles = tuple(_normalize_tile_row(row) for row in tile_rows)
    meta = _normalize_layout_metadata(layout_metadata)
    return BoardConfig.from_tile_metadata(tiles, layout_metadata=meta)


def load_layout_metadata_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BoardLayoutLoadError("Board layout metadata JSON must be an object")
    return payload


def _default_sidecar_metadata_path(csv_path: str | Path) -> Path:
    csv_path = Path(csv_path)
    return csv_path.with_name(f"{csv_path.stem}_meta.json")


def load_board_config_from_json(path: str | Path) -> BoardConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "tiles" not in payload:
        raise BoardLayoutLoadError("JSON board layout must be an object with a 'tiles' field")
    if not isinstance(payload["tiles"], list):
        raise BoardLayoutLoadError("'tiles' must be a list")
    return build_board_config_from_rows(payload["tiles"], layout_metadata=payload.get("layout_metadata"))


def load_board_config_from_csv(path: str | Path, *, metadata_path: str | Path | None = None) -> BoardConfig:
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    layout_metadata = None
    resolved_meta = Path(metadata_path) if metadata_path else _default_sidecar_metadata_path(path)
    if resolved_meta.exists():
        layout_metadata = load_layout_metadata_json(resolved_meta)
    return build_board_config_from_rows(rows, layout_metadata=layout_metadata)


def load_board_config(path: str | Path, *, metadata_path: str | Path | None = None) -> BoardConfig:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return load_board_config_from_json(path)
    if suffix == ".csv":
        return load_board_config_from_csv(path, metadata_path=metadata_path)
    raise BoardLayoutLoadError(f"Unsupported board layout file format: {suffix}")
