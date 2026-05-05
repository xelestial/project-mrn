from __future__ import annotations

import asyncio

from apps.server.src.services.stream_service import StreamService
from apps.server.tests.prompt_payloads import module_prompt


def _source_messages(messages):
    return [message for message in messages if message.type != "view_commit"]


def test_same_idempotency_key_returns_existing_message() -> None:
    service = StreamService()

    async def _run() -> None:
        first = await service.publish("s1", "event", {"event_type": "dice_roll", "idempotency_key": "idem:1"})
        second = await service.publish("s1", "event", {"event_type": "dice_roll", "idempotency_key": "idem:1", "dice": [6]})

        assert first.seq == second.seq
        assert len(_source_messages(await service.snapshot("s1"))) == 1

    asyncio.run(_run())

def test_same_event_type_different_module_id_publishes_twice() -> None:
    service = StreamService()

    async def _run() -> None:
        await service.publish(
            "s1",
            "event",
            {
                "event_type": "dice_roll",
                "runtime_module": {"module_id": "mod:dice:1", "idempotency_key": "idem:1"},
            },
        )
        await service.publish(
            "s1",
            "event",
            {
                "event_type": "dice_roll",
                "runtime_module": {"module_id": "mod:dice:2", "idempotency_key": "idem:2"},
            },
        )

        assert len(_source_messages(await service.snapshot("s1"))) == 2

    asyncio.run(_run())


def test_request_scoped_prompt_ignores_shared_module_idempotency_key() -> None:
    service = StreamService()

    async def _run() -> None:
        first = await service.publish(
            "s1",
            "prompt",
            module_prompt({
                "request_id": "req:draft",
                "request_type": "draft_card",
                "player_id": 1,
                "idempotency_key": "module:draft",
            }),
        )
        second = await service.publish(
            "s1",
            "prompt",
            module_prompt({
                "request_id": "req:final",
                "request_type": "final_character",
                "player_id": 1,
                "idempotency_key": "module:draft",
            }),
        )
        duplicate = await service.publish(
            "s1",
            "prompt",
            module_prompt({
                "request_id": "req:final",
                "request_type": "final_character",
                "player_id": 1,
                "idempotency_key": "module:draft:retry",
            }),
        )
        snapshot = await service.snapshot("s1")

        assert first.seq == 1
        assert second.seq == 3
        assert duplicate.seq == second.seq
        assert [message.payload["request_id"] for message in _source_messages(snapshot)] == ["req:draft", "req:final"]

    asyncio.run(_run())


def test_request_scoped_decision_event_ignores_shared_module_idempotency_key() -> None:
    service = StreamService()

    async def _run() -> None:
        first = await service.publish(
            "s1",
            "event",
            {
                "event_type": "decision_requested",
                "request_id": "req:draft",
                "request_type": "draft_card",
                "player_id": 1,
                "idempotency_key": "module:draft",
            },
        )
        second = await service.publish(
            "s1",
            "event",
            {
                "event_type": "decision_requested",
                "request_id": "req:final",
                "request_type": "final_character",
                "player_id": 1,
                "idempotency_key": "module:draft",
            },
        )
        duplicate = await service.publish(
            "s1",
            "event",
            {
                "event_type": "decision_requested",
                "request_id": "req:final",
                "request_type": "final_character",
                "player_id": 1,
                "idempotency_key": "module:draft:retry",
            },
        )
        snapshot = await service.snapshot("s1")

        assert first.seq == 1
        assert second.seq == 3
        assert duplicate.seq == second.seq
        assert [message.payload["request_id"] for message in _source_messages(snapshot)] == ["req:draft", "req:final"]

    asyncio.run(_run())
