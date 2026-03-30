from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict

from apps.server.src.domain.session_models import SeatConfig, SeatType, Session, SessionStatus, utc_now_iso
from apps.server.src.services.parameter_service import (
    GameParameterResolver,
    ParameterValidationError,
    PublicManifestBuilder,
)
from apps.server.src.services.persistence import SessionStore


class SessionStateError(ValueError):
    """Raised when an operation cannot be performed in current session state."""


class SessionNotFoundError(KeyError):
    """Raised when a session_id lookup fails."""


class SessionService:
    """In-memory session lifecycle service for B1 baseline."""

    def __init__(
        self,
        parameter_resolver: GameParameterResolver | None = None,
        manifest_builder: PublicManifestBuilder | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._parameter_resolver = parameter_resolver or GameParameterResolver()
        self._manifest_builder = manifest_builder or PublicManifestBuilder()
        self._session_store = session_store
        self._load_from_store()

    def create_session(
        self,
        seats: list[dict],
        config: dict | None = None,
    ) -> Session:
        raw_config = dict(config or {})
        try:
            resolved_parameters = self._parameter_resolver.resolve(raw_config)
        except ParameterValidationError as exc:
            raise SessionStateError(str(exc)) from exc
        normalized = self._normalize_seats(seats, resolved_parameters["seats"])
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        host_token = self._new_token("host")
        join_tokens: dict[int, str] = {}

        for seat in normalized:
            if seat.seat_type == SeatType.HUMAN:
                join_tokens[seat.seat] = self._new_token(f"seat{seat.seat}")

        session = Session(
            session_id=session_id,
            status=SessionStatus.WAITING,
            seats=normalized,
            config=raw_config,
            host_token=host_token,
            join_tokens=join_tokens,
            resolved_parameters=resolved_parameters,
            parameter_manifest=self._manifest_builder.build_public_manifest(resolved_parameters),
        )
        self._sessions[session_id] = session
        self._persist_sessions()
        return session

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def join_session(self, session_id: str, seat: int, join_token: str, display_name: str | None = None) -> dict:
        del display_name  # reserved for future profile storage
        session = self.get_session(session_id)
        if session.status != SessionStatus.WAITING:
            raise SessionStateError("session_not_joinable")

        token_expected = session.join_tokens.get(seat)
        if token_expected is None or token_expected != join_token:
            raise SessionStateError("invalid_join_token")

        seat_cfg = self._find_seat(session, seat)
        if seat_cfg.seat_type != SeatType.HUMAN:
            raise SessionStateError("seat_not_human")
        if seat_cfg.player_id is not None:
            raise SessionStateError("seat_already_joined")

        seat_cfg.player_id = seat
        seat_cfg.connected = True
        session_token = self._new_token(f"session_p{seat}")
        session.session_tokens[seat] = session_token
        self._persist_sessions()
        return {
            "session_id": session.session_id,
            "seat": seat,
            "player_id": seat_cfg.player_id,
            "session_token": session_token,
            "role": "seat",
        }

    def start_session(self, session_id: str, host_token: str) -> Session:
        session = self.get_session(session_id)
        if session.host_token != host_token:
            raise SessionStateError("invalid_host_token")
        if session.status != SessionStatus.WAITING:
            raise SessionStateError("session_not_startable")
        if not self._all_required_humans_joined(session):
            raise SessionStateError("human_seats_not_ready")
        session.status = SessionStatus.IN_PROGRESS
        session.started_at = utc_now_iso()
        self._persist_sessions()
        return session

    def to_public(self, session: Session) -> dict:
        return {
            "session_id": session.session_id,
            "status": session.status.value,
            "round_index": session.round_index,
            "turn_index": session.turn_index,
            "created_at": session.created_at,
            "started_at": session.started_at,
            "seats": [self._seat_public(s) for s in session.seats],
            "parameter_manifest": dict(session.parameter_manifest),
        }

    def verify_session_token(self, session_id: str, token: str | None) -> dict:
        session = self.get_session(session_id)
        if not token:
            return {"role": "spectator", "seat": None, "player_id": None}
        for seat, issued in session.session_tokens.items():
            if issued == token:
                seat_cfg = self._find_seat(session, seat)
                return {"role": "seat", "seat": seat, "player_id": seat_cfg.player_id}
        raise SessionStateError("invalid_session_token")

    def mark_connected(self, session_id: str, seat: int, connected: bool) -> None:
        session = self.get_session(session_id)
        seat_cfg = self._find_seat(session, seat)
        seat_cfg.connected = connected
        self._persist_sessions()

    def is_all_ai(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        return all(seat.seat_type == SeatType.AI for seat in session.seats)

    def finish_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        if session.status == SessionStatus.IN_PROGRESS:
            session.status = SessionStatus.FINISHED
            self._persist_sessions()

    def to_create_result(self, session: Session) -> dict:
        data = self.to_public(session)
        data["host_token"] = session.host_token
        data["join_tokens"] = {str(k): v for k, v in session.join_tokens.items()}
        return data

    @staticmethod
    def _seat_public(seat: SeatConfig) -> dict:
        payload = asdict(seat)
        payload["seat_type"] = seat.seat_type.value
        return payload

    @staticmethod
    def _new_token(prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(16)}"

    @staticmethod
    def _normalize_seats(seats: list[dict], seat_limits: dict) -> list[SeatConfig]:
        min_seat_count = int(seat_limits.get("min", 1))
        max_seat_count = int(seat_limits.get("max", 4))
        allowed_seats = {int(v) for v in seat_limits.get("allowed", list(range(1, max_seat_count + 1)))}
        if len(seats) < min_seat_count:
            raise SessionStateError("seat_count_below_min")
        if len(seats) > max_seat_count:
            raise SessionStateError("seat_count_above_max")
        seen: set[int] = set()
        result: list[SeatConfig] = []
        for raw in seats:
            seat = int(raw.get("seat", -1))
            if seat not in allowed_seats:
                raise SessionStateError("seat_out_of_range")
            if seat in seen:
                raise SessionStateError("seat_duplicate")
            seen.add(seat)
            seat_type = str(raw.get("seat_type", "")).strip().lower()
            if seat_type not in (SeatType.HUMAN.value, SeatType.AI.value):
                raise SessionStateError("invalid_seat_type")
            ai_profile = raw.get("ai_profile")
            if seat_type == SeatType.HUMAN.value and ai_profile:
                raise SessionStateError("human_seat_cannot_have_ai_profile")
            result.append(
                SeatConfig(
                    seat=seat,
                    seat_type=SeatType(seat_type),
                    ai_profile=str(ai_profile) if ai_profile is not None else None,
                )
            )
        result.sort(key=lambda s: s.seat)
        return result

    @staticmethod
    def _find_seat(session: Session, seat: int) -> SeatConfig:
        for seat_cfg in session.seats:
            if seat_cfg.seat == seat:
                return seat_cfg
        raise SessionStateError("seat_not_found")

    @staticmethod
    def _all_required_humans_joined(session: Session) -> bool:
        for seat in session.seats:
            if seat.seat_type == SeatType.HUMAN and seat.player_id is None:
                return False
        return True

    def _persist_sessions(self) -> None:
        if self._session_store is None:
            return
        payload = [self._session_to_payload(session) for session in self._sessions.values()]
        self._session_store.save_sessions(payload)

    def _load_from_store(self) -> None:
        if self._session_store is None:
            return
        for raw in self._session_store.load_sessions():
            try:
                session = self._session_from_payload(raw)
            except Exception:
                continue
            if not session.session_id:
                continue
            self._sessions[session.session_id] = session

    @staticmethod
    def _session_to_payload(session: Session) -> dict:
        return {
            "session_id": session.session_id,
            "status": session.status.value,
            "seats": [
                {
                    "seat": seat.seat,
                    "seat_type": seat.seat_type.value,
                    "ai_profile": seat.ai_profile,
                    "player_id": seat.player_id,
                    "connected": seat.connected,
                }
                for seat in session.seats
            ],
            "config": dict(session.config),
            "created_at": session.created_at,
            "started_at": session.started_at,
            "round_index": session.round_index,
            "turn_index": session.turn_index,
            "host_token": session.host_token,
            "join_tokens": {str(k): v for k, v in session.join_tokens.items()},
            "session_tokens": {str(k): v for k, v in session.session_tokens.items()},
            "resolved_parameters": dict(session.resolved_parameters),
            "parameter_manifest": dict(session.parameter_manifest),
        }

    @staticmethod
    def _session_from_payload(payload: dict) -> Session:
        seats_raw = payload.get("seats", [])
        seats: list[SeatConfig] = []
        for item in seats_raw:
            if not isinstance(item, dict):
                continue
            seat_type = SeatType(str(item.get("seat_type", SeatType.AI.value)))
            seats.append(
                SeatConfig(
                    seat=int(item.get("seat", 0)),
                    seat_type=seat_type,
                    ai_profile=item.get("ai_profile"),
                    player_id=int(item["player_id"]) if item.get("player_id") is not None else None,
                    connected=bool(item.get("connected", False)),
                )
            )
        return Session(
            session_id=str(payload.get("session_id", "")),
            status=SessionStatus(str(payload.get("status", SessionStatus.WAITING.value))),
            seats=sorted(seats, key=lambda s: s.seat),
            config=dict(payload.get("config", {})),
            created_at=str(payload.get("created_at", utc_now_iso())),
            started_at=payload.get("started_at"),
            round_index=int(payload.get("round_index", 0)),
            turn_index=int(payload.get("turn_index", 0)),
            host_token=str(payload.get("host_token", "")),
            join_tokens={int(k): str(v) for k, v in dict(payload.get("join_tokens", {})).items()},
            session_tokens={int(k): str(v) for k, v in dict(payload.get("session_tokens", {})).items()},
            resolved_parameters=dict(payload.get("resolved_parameters", {})),
            parameter_manifest=dict(payload.get("parameter_manifest", {})),
        )
