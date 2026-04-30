from __future__ import annotations

import secrets
from dataclasses import asdict

from apps.server.src.domain.room_models import Room, RoomSeat, RoomStatus
from apps.server.src.domain.session_models import (
    ParticipantClientType,
    SeatType,
    SessionVisibility,
    utc_now_iso,
)
from apps.server.src.services.persistence import RoomStore
from apps.server.src.services.session_service import SessionStateError


class RoomStateError(ValueError):
    """Raised when a room operation is invalid for the current room state."""


class RoomNotFoundError(KeyError):
    """Raised when a room lookup fails."""

class RoomService:
    def __init__(self, session_service, room_store: RoomStore | None = None) -> None:
        self._session_service = session_service
        self._room_store = room_store
        self._rooms: dict[int, Room] = {}
        self._session_to_room: dict[str, int] = {}
        self._next_room_no = 1
        self._load_from_store()

    def create_room(
        self,
        *,
        room_title: str,
        seats: list[dict],
        host_seat: int,
        nickname: str,
        config: dict | None = None,
    ) -> dict:
        normalized_title = self._normalize_room_title(room_title)
        normalized_nickname = self._normalize_nickname(nickname)
        if self._title_in_use(normalized_title):
            raise RoomStateError("room_title_already_exists")
        raw_config = dict(config or {})
        try:
            visibility = self._session_service.normalize_visibility(raw_config)
        except SessionStateError as exc:
            raise RoomStateError(str(exc)) from exc
        raw_config["visibility"] = visibility.value
        room_seats = self._normalize_room_seats(seats)
        host_cfg = self._find_room_seat(room_seats, host_seat)
        if host_cfg.seat_type != SeatType.HUMAN:
            raise RoomStateError("host_seat_must_be_human")

        room_no = self._next_room_no
        self._next_room_no += 1
        host_token = self._new_token(f"room{room_no}_seat{host_seat}")
        host_cfg.player_id = host_seat
        host_cfg.nickname = normalized_nickname
        host_cfg.ready = False
        host_cfg.connected = False
        host_cfg.room_member_token = host_token

        room = Room(
            room_no=room_no,
            room_title=normalized_title,
            status=RoomStatus.WAITING,
            seats=room_seats,
            host_seat=host_seat,
            visibility=visibility,
            config=raw_config,
        )
        self._rooms[room_no] = room
        self._persist_rooms()
        return {
            "room": self.to_public(room),
            "room_member_token": host_token,
            "seat": host_seat,
            "nickname": normalized_nickname,
        }

    def list_rooms(self) -> list[Room]:
        return [self._rooms[key] for key in sorted(self._rooms)]

    def get_room(self, room_no: int) -> Room:
        room = self._rooms.get(int(room_no))
        if room is None:
            raise RoomNotFoundError(room_no)
        return room

    def find_room_for_session(self, session_id: str) -> Room | None:
        room_no = self._session_to_room.get(str(session_id))
        if room_no is None:
            return None
        return self._rooms.get(room_no)

    def join_room(self, *, room_no: int, seat: int, nickname: str) -> dict:
        room = self.get_room(room_no)
        if room.status != RoomStatus.WAITING:
            raise RoomStateError("room_not_joinable")
        seat_cfg = self._find_room_seat(room.seats, seat)
        if seat_cfg.seat_type != SeatType.HUMAN:
            raise RoomStateError("seat_not_human")
        if seat_cfg.player_id is not None:
            raise RoomStateError("seat_already_joined")
        seat_cfg.player_id = seat
        seat_cfg.nickname = self._normalize_nickname(nickname)
        seat_cfg.ready = False
        seat_cfg.connected = False
        seat_cfg.room_member_token = self._new_token(f"room{room_no}_seat{seat}")
        self._persist_rooms()
        return {
            "room": self.to_public(room),
            "room_member_token": seat_cfg.room_member_token,
            "seat": seat,
            "nickname": seat_cfg.nickname,
        }

    def set_ready(self, *, room_no: int, room_member_token: str, ready: bool) -> dict:
        room, seat_cfg = self._authenticate_member(room_no, room_member_token)
        if room.status != RoomStatus.WAITING:
            raise RoomStateError("room_not_waiting")
        if seat_cfg.seat_type != SeatType.HUMAN:
            raise RoomStateError("seat_not_human")
        seat_cfg.ready = bool(ready)
        self._persist_rooms()
        return self.to_public(room)

    def leave_room(self, *, room_no: int, room_member_token: str) -> dict:
        room, seat_cfg = self._authenticate_member(room_no, room_member_token)
        if room.status != RoomStatus.WAITING:
            raise RoomStateError("room_not_leavable")
        if seat_cfg.seat_type == SeatType.AI:
            raise RoomStateError("seat_not_human")
        seat_cfg.player_id = None
        seat_cfg.nickname = None
        seat_cfg.ready = False
        seat_cfg.connected = False
        seat_cfg.room_member_token = None
        seat_cfg.session_token = None
        if seat_cfg.seat == room.host_seat:
            self._close_room(room.room_no)
            raise RoomNotFoundError(room_no)
        self._persist_rooms()
        return self.to_public(room)

    def resume_room(self, *, room_no: int, room_member_token: str) -> dict:
        room, seat_cfg = self._authenticate_member(room_no, room_member_token)
        payload = self.to_public(room, include_private_session_id=True)
        payload["member_seat"] = seat_cfg.seat
        payload["member_nickname"] = seat_cfg.nickname
        if seat_cfg.session_token:
            payload["session_token"] = seat_cfg.session_token
        return payload

    def start_room(self, *, room_no: int, room_member_token: str) -> dict:
        room, seat_cfg = self._authenticate_member(room_no, room_member_token)
        if seat_cfg.seat != room.host_seat:
            raise RoomStateError("only_host_can_start")
        if room.status != RoomStatus.WAITING:
            raise RoomStateError("room_not_startable")
        if not self._all_human_seats_joined(room):
            raise RoomStateError("human_seats_not_joined")
        if not self._all_human_seats_ready(room):
            raise RoomStateError("human_seats_not_ready")

        session = self._session_service.create_session(
            seats=[self._room_seat_to_session_input(seat) for seat in room.seats],
            config=room.config,
        )
        for human_seat in [seat for seat in room.seats if seat.seat_type == SeatType.HUMAN]:
            result = self._session_service.join_session(
                session.session_id,
                human_seat.seat,
                session.join_tokens[human_seat.seat],
                human_seat.nickname,
            )
            human_seat.session_token = str(result["session_token"])
        room.status = RoomStatus.IN_PROGRESS
        room.started_at = utc_now_iso()
        room.session_id = session.session_id
        self._session_to_room[session.session_id] = room.room_no
        self._persist_rooms()
        return {
            "room": self.to_public(room, include_private_session_id=True),
            "session_id": session.session_id,
            "session_tokens": {
                str(seat.seat): seat.session_token
                for seat in room.seats
                if seat.seat_type == SeatType.HUMAN and seat.session_token
            },
        }

    def handle_session_finished(self, session_id: str) -> None:
        room_no = self._session_to_room.get(session_id)
        if room_no is None:
            return
        try:
            room = self.get_room(room_no)
        except RoomNotFoundError:
            self._session_to_room.pop(session_id, None)
            return
        room.status = RoomStatus.CLOSED
        room.closed_at = utc_now_iso()
        for seat in room.seats:
            seat.room_member_token = None
            seat.session_token = None
        self._session_service.expire_session_tokens(session_id)
        self._close_room(room_no)

    def to_public(self, room: Room, *, include_private_session_id: bool = False) -> dict:
        human_joined = sum(1 for seat in room.seats if seat.seat_type == SeatType.HUMAN and seat.player_id is not None)
        human_total = sum(1 for seat in room.seats if seat.seat_type == SeatType.HUMAN)
        ready_count = sum(1 for seat in room.seats if seat.seat_type == SeatType.HUMAN and seat.ready)
        payload = {
            "room_no": room.room_no,
            "room_title": room.room_title,
            "status": room.status.value,
            "visibility": room.visibility.value,
            "host_seat": room.host_seat,
            "created_at": room.created_at,
            "started_at": room.started_at,
            "human_joined_count": human_joined,
            "human_total_count": human_total,
            "human_ready_count": ready_count,
            "seats": [self._room_seat_public(seat) for seat in room.seats],
        }
        if room.session_id and (include_private_session_id or room.visibility == SessionVisibility.PUBLIC):
            payload["session_id"] = room.session_id
        return payload

    @staticmethod
    def _room_seat_to_session_input(seat: RoomSeat) -> dict:
        return {
            "seat": seat.seat,
            "seat_type": seat.seat_type.value,
            "ai_profile": seat.ai_profile,
            "participant_client": seat.participant_client.value if seat.participant_client is not None else None,
            "participant_config": dict(seat.participant_config),
        }

    @staticmethod
    def _room_seat_public(seat: RoomSeat) -> dict:
        payload = asdict(seat)
        payload["seat_type"] = seat.seat_type.value
        payload["participant_client"] = seat.participant_client.value if seat.participant_client is not None else None
        payload.pop("room_member_token", None)
        payload.pop("session_token", None)
        return payload

    @staticmethod
    def _normalize_room_title(room_title: str) -> str:
        title = str(room_title or "").strip()
        if not title:
            raise RoomStateError("room_title_required")
        return title

    @staticmethod
    def _normalize_nickname(nickname: str) -> str:
        value = str(nickname or "").strip()
        if not value:
            raise RoomStateError("nickname_required")
        return value[:24]

    @staticmethod
    def _new_token(prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(16)}"

    def _title_in_use(self, normalized_title: str) -> bool:
        lowered = normalized_title.casefold()
        return any(room.room_title.casefold() == lowered for room in self._rooms.values())

    @staticmethod
    def _normalize_room_seats(seats: list[dict]) -> list[RoomSeat]:
        if not seats:
            raise RoomStateError("room_requires_seats")
        normalized: list[RoomSeat] = []
        seen: set[int] = set()
        for raw in seats:
            seat = int(raw.get("seat", 0))
            if seat <= 0:
                raise RoomStateError("invalid_seat")
            if seat in seen:
                raise RoomStateError("seat_duplicate")
            seen.add(seat)
            seat_type = SeatType(str(raw.get("seat_type", SeatType.HUMAN.value)).strip().lower())
            participant_client_raw = raw.get("participant_client")
            if participant_client_raw is None:
                participant_client = (
                    ParticipantClientType.HUMAN_HTTP
                    if seat_type == SeatType.HUMAN
                    else ParticipantClientType.LOCAL_AI
                )
            else:
                participant_client = ParticipantClientType(str(participant_client_raw).strip().lower())
            participant_config_raw = raw.get("participant_config", {})
            participant_config = dict(participant_config_raw or {})
            ai_profile = str(raw["ai_profile"]) if raw.get("ai_profile") is not None else None
            room_seat = RoomSeat(
                seat=seat,
                seat_type=seat_type,
                ai_profile=ai_profile,
                participant_client=participant_client,
                participant_config=participant_config,
            )
            if seat_type == SeatType.AI:
                room_seat.player_id = seat
                room_seat.nickname = f"AI {seat}"
                room_seat.ready = True
            normalized.append(room_seat)
        normalized.sort(key=lambda item: item.seat)
        return normalized

    @staticmethod
    def _find_room_seat(seats: list[RoomSeat], seat: int) -> RoomSeat:
        for seat_cfg in seats:
            if seat_cfg.seat == int(seat):
                return seat_cfg
        raise RoomStateError("seat_not_found")

    def _authenticate_member(self, room_no: int, room_member_token: str) -> tuple[Room, RoomSeat]:
        room = self.get_room(room_no)
        for seat in room.seats:
            if seat.room_member_token and seat.room_member_token == room_member_token:
                return room, seat
        raise RoomStateError("invalid_room_member_token")

    @staticmethod
    def _all_human_seats_joined(room: Room) -> bool:
        return all(seat.player_id is not None for seat in room.seats if seat.seat_type == SeatType.HUMAN)

    @staticmethod
    def _all_human_seats_ready(room: Room) -> bool:
        return all(seat.ready for seat in room.seats if seat.seat_type == SeatType.HUMAN)

    def _close_room(self, room_no: int) -> None:
        room = self._rooms.pop(room_no, None)
        if room and room.session_id:
            self._session_to_room.pop(room.session_id, None)
        self._persist_rooms()

    def _persist_rooms(self) -> None:
        if self._room_store is None:
            return
        payload = {
            "next_room_no": self._next_room_no,
            "rooms": [self._room_to_payload(room) for room in self.list_rooms()],
        }
        self._room_store.save_room_state(payload)

    def _load_from_store(self) -> None:
        if self._room_store is None:
            return
        payload = self._room_store.load_room_state()
        next_room_no = payload.get("next_room_no")
        if isinstance(next_room_no, int) and next_room_no >= 1:
            self._next_room_no = next_room_no
        for raw in payload.get("rooms", []):
            if not isinstance(raw, dict):
                continue
            try:
                room = self._room_from_payload(raw)
            except Exception:
                continue
            self._rooms[room.room_no] = room
            if room.session_id:
                self._session_to_room[room.session_id] = room.room_no

    @staticmethod
    def _room_to_payload(room: Room) -> dict:
        return {
            "room_no": room.room_no,
            "room_title": room.room_title,
            "status": room.status.value,
            "visibility": room.visibility.value,
            "host_seat": room.host_seat,
            "config": dict(room.config),
            "created_at": room.created_at,
            "started_at": room.started_at,
            "closed_at": room.closed_at,
            "session_id": room.session_id,
            "seats": [
                {
                    "seat": seat.seat,
                    "seat_type": seat.seat_type.value,
                    "ai_profile": seat.ai_profile,
                    "participant_client": seat.participant_client.value if seat.participant_client is not None else None,
                    "participant_config": dict(seat.participant_config),
                    "player_id": seat.player_id,
                    "nickname": seat.nickname,
                    "ready": seat.ready,
                    "connected": seat.connected,
                    "room_member_token": seat.room_member_token,
                    "session_token": seat.session_token,
                }
                for seat in room.seats
            ],
        }

    @staticmethod
    def _room_from_payload(raw: dict) -> Room:
        seats: list[RoomSeat] = []
        for item in raw.get("seats", []):
            if not isinstance(item, dict):
                continue
            seat_type = SeatType(str(item.get("seat_type", SeatType.HUMAN.value)))
            participant_default = (
                ParticipantClientType.HUMAN_HTTP
                if seat_type == SeatType.HUMAN
                else ParticipantClientType.LOCAL_AI
            )
            participant_client_raw = item.get("participant_client")
            seats.append(
                RoomSeat(
                    seat=int(item.get("seat", 0)),
                    seat_type=seat_type,
                    ai_profile=item.get("ai_profile"),
                    participant_client=ParticipantClientType(str(participant_client_raw or participant_default.value)),
                    participant_config=dict(item.get("participant_config", {})),
                    player_id=int(item["player_id"]) if item.get("player_id") is not None else None,
                    nickname=item.get("nickname"),
                    ready=bool(item.get("ready", False)),
                    connected=bool(item.get("connected", False)),
                    room_member_token=item.get("room_member_token"),
                    session_token=item.get("session_token"),
                )
            )
        return Room(
            room_no=int(raw.get("room_no", 0)),
            room_title=str(raw.get("room_title", "")),
            status=RoomStatus(str(raw.get("status", RoomStatus.WAITING.value))),
            seats=sorted(seats, key=lambda seat: seat.seat),
            host_seat=int(raw.get("host_seat", 1)),
            visibility=SessionVisibility(str(raw.get("visibility") or dict(raw.get("config", {})).get("visibility") or SessionVisibility.PRIVATE.value)),
            config=dict(raw.get("config", {})),
            created_at=str(raw.get("created_at", utc_now_iso())),
            started_at=raw.get("started_at"),
            closed_at=raw.get("closed_at"),
            session_id=raw.get("session_id"),
        )
