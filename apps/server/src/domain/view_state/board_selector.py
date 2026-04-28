from __future__ import annotations

from typing import Any

from .types import BoardLastMoveViewState, BoardTileViewState, BoardViewState


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _event_type(payload: dict[str, Any]) -> str:
    event_type = payload.get("event_type")
    return event_type if isinstance(event_type, str) and event_type.strip() else ""


def _integer_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


def _score_coin_count(raw: dict[str, Any]) -> int:
    value = raw.get("score_coin_count")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = raw.get("score_coins")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = raw.get("tile_score_coins")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _parse_snapshot_players(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    explicit_snapshot = _record(payload.get("snapshot")) or {}
    players = explicit_snapshot.get("players")
    if isinstance(players, list):
        return [item for item in players if isinstance(item, dict)]
    players = payload.get("players")
    if isinstance(players, list):
        return [item for item in players if isinstance(item, dict)]
    return None


def _parse_snapshot_tiles(payload: dict[str, Any]) -> list[BoardTileViewState] | None:
    explicit_snapshot = _record(payload.get("snapshot")) or {}
    snapshot_board = _record(explicit_snapshot.get("board")) or {}
    tiles = snapshot_board.get("tiles")
    if not isinstance(tiles, list):
        return None
    parsed: list[BoardTileViewState] = []
    for fallback_index, raw in enumerate(tiles):
        record = _record(raw)
        if not record:
            continue
        tile_index = _number(record.get("tile_index"))
        if tile_index is None:
            tile_index = fallback_index
        parsed.append(
            {
                "tile_index": tile_index,
                "score_coin_count": _score_coin_count(record),
                "owner_player_id": _number(record.get("owner_player_id")),
                "pawn_player_ids": _integer_list(record.get("pawn_player_ids")),
            }
        )
    return parsed


def _latest_board_snapshot_entry(messages: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]], list[BoardTileViewState], dict[str, Any]] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        players = _parse_snapshot_players(payload)
        explicit_snapshot = _record(payload.get("snapshot")) or {}
        snapshot_board = _record(explicit_snapshot.get("board")) or {}
        tiles = _parse_snapshot_tiles(payload)
        if players is None or tiles is None:
            continue
        return index, players, tiles, snapshot_board
    return None


def build_board_view_state(messages: list[dict[str, Any]]) -> BoardViewState | None:
    last_move: BoardLastMoveViewState | None = None
    snapshot_entry = _latest_board_snapshot_entry(messages)
    live_tiles: list[BoardTileViewState] = []
    f_value: int | float | None = None

    if snapshot_entry is not None:
      snapshot_index, snapshot_players, snapshot_tiles, snapshot_board = snapshot_entry
      live_tiles = [dict(tile) for tile in snapshot_tiles]
      raw_f_value = snapshot_board.get("f_value")
      if isinstance(raw_f_value, (int, float)) and not isinstance(raw_f_value, bool):
          f_value = raw_f_value
      tile_by_index = {tile["tile_index"]: tile for tile in live_tiles}
      player_positions: dict[int, int] = {}
      alive_players: set[int] = set()

      for raw_player in snapshot_players:
          player_id = _number(raw_player.get("player_id"))
          position = _number(raw_player.get("position"))
          alive = raw_player.get("alive")
          if player_id is None:
              continue
          if position is not None:
              player_positions[player_id] = position
          if alive is not False:
              alive_players.add(player_id)

      for message in messages[snapshot_index + 1 :]:
          if message.get("type") != "event":
              continue
          payload = _record(message.get("payload")) or {}
          public_context = _record(payload.get("public_context")) or {}
          event_code = _event_type(payload)
          event_actor_id = _number(payload.get("acting_player_id", payload.get("player_id")))
          event_f_value = payload.get("f_value", public_context.get("f_value"))
          if isinstance(event_f_value, (int, float)) and not isinstance(event_f_value, bool):
              f_value = event_f_value
          if event_code == "f_value_change":
              event_f_after = payload.get("after")
              if isinstance(event_f_after, (int, float)) and not isinstance(event_f_after, bool):
                  f_value = event_f_after
          context_position = _number(public_context.get("player_position"))
          if event_actor_id is not None and context_position is not None:
              player_positions[event_actor_id] = context_position
          context_tile_index = _number(public_context.get("tile_index"))
          if context_tile_index is not None and context_tile_index in tile_by_index:
              if (
                  "tile_score_coins" in public_context
                  or "score_coin_count" in public_context
                  or "score_coins" in public_context
              ):
                  tile_by_index[context_tile_index]["score_coin_count"] = _score_coin_count(public_context)
          if event_code == "player_move" and event_actor_id is not None:
              to_tile_index = _number(payload.get("to_tile_index", payload.get("to_tile", payload.get("to_pos"))))
              if to_tile_index is not None:
                  player_positions[event_actor_id] = to_tile_index
          if event_code == "tile_purchased":
              tile_index = _number(payload.get("tile_index", payload.get("position", payload.get("tile"))))
              owner_player_id = _number(payload.get("owner_player_id", payload.get("acting_player_id", payload.get("player_id"))))
              if tile_index is not None and tile_index in tile_by_index and owner_player_id is not None:
                  tile = tile_by_index[tile_index]
                  tile["owner_player_id"] = owner_player_id
                  if (
                      "tile_score_coins" in payload
                      or "score_coin_count" in payload
                      or "score_coins" in payload
                  ):
                      tile["score_coin_count"] = _score_coin_count(payload)

      for tile in live_tiles:
          tile["pawn_player_ids"] = []
      for player_id, position in player_positions.items():
          if player_id not in alive_players:
              continue
          tile = tile_by_index.get(position)
          if tile is not None:
              tile["pawn_player_ids"] = [*tile["pawn_player_ids"], player_id]
      for tile in live_tiles:
          tile["pawn_player_ids"].sort()

    for message in reversed(messages):
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        if _event_type(payload) != "player_move":
            continue
        last_move = {
            "player_id": _number(payload.get("acting_player_id", payload.get("player_id"))),
            "from_tile_index": _number(payload.get("from_tile_index", payload.get("from_tile", payload.get("from_pos")))),
            "to_tile_index": _number(payload.get("to_tile_index", payload.get("to_tile", payload.get("to_pos")))),
            "path_tile_indices": _integer_list(payload.get("path")),
        }
        break

    if last_move is None and not live_tiles:
        return None
    result: BoardViewState = {
        "last_move": last_move,
        "tiles": live_tiles,
    }
    if f_value is not None:
        result["f_value"] = f_value
    return result
