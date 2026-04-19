from __future__ import annotations

import unittest

from apps.server.src.services.room_service import (
    RoomNotFoundError,
    RoomService,
    RoomStateError,
)
from apps.server.src.services.session_service import SessionService


def _room_seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "human"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
    ]


class RoomServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions = SessionService()
        self.rooms = RoomService(session_service=self.sessions)

    def test_create_join_ready_start_room(self) -> None:
        created = self.rooms.create_room(
            room_title="Alpha Room",
            seats=_room_seats(),
            host_seat=1,
            nickname="Host",
            config={"seed": 42},
        )
        room = created["room"]
        self.assertEqual(room["room_no"], 1)
        self.assertEqual(room["room_title"], "Alpha Room")
        self.assertEqual(room["seats"][0]["nickname"], "Host")
        self.assertTrue(room["seats"][2]["ready"])

        joined = self.rooms.join_room(room_no=1, seat=2, nickname="Guest")
        guest_token = joined["room_member_token"]
        self.assertEqual(joined["room"]["seats"][1]["nickname"], "Guest")

        self.rooms.set_ready(room_no=1, room_member_token=created["room_member_token"], ready=True)
        public = self.rooms.set_ready(room_no=1, room_member_token=guest_token, ready=True)
        self.assertEqual(public["human_ready_count"], 2)

        started = self.rooms.start_room(room_no=1, room_member_token=created["room_member_token"])
        self.assertIsNotNone(started["session_id"])
        session = self.sessions.get_session(started["session_id"])
        self.assertEqual(session.seats[0].display_name, "Host")
        self.assertEqual(session.seats[1].display_name, "Guest")

    def test_room_title_must_be_unique(self) -> None:
        self.rooms.create_room(
            room_title="Alpha Room",
            seats=_room_seats(),
            host_seat=1,
            nickname="Host",
        )
        with self.assertRaises(RoomStateError):
            self.rooms.create_room(
                room_title="Alpha Room",
                seats=_room_seats(),
                host_seat=1,
                nickname="Another Host",
            )

    def test_room_removed_after_finished_session(self) -> None:
        created = self.rooms.create_room(
            room_title="Alpha Room",
            seats=_room_seats(),
            host_seat=1,
            nickname="Host",
        )
        guest = self.rooms.join_room(room_no=1, seat=2, nickname="Guest")
        self.rooms.set_ready(room_no=1, room_member_token=created["room_member_token"], ready=True)
        self.rooms.set_ready(room_no=1, room_member_token=guest["room_member_token"], ready=True)
        started = self.rooms.start_room(room_no=1, room_member_token=created["room_member_token"])

        self.sessions.start_session(started["session_id"], self.sessions.get_session(started["session_id"]).host_token)
        self.rooms.handle_session_finished(started["session_id"])

        with self.assertRaises(RoomNotFoundError):
            self.rooms.get_room(1)
        with self.assertRaises(Exception):
            self.sessions.verify_session_token(
                started["session_id"],
                started["session_tokens"]["1"],
            )
