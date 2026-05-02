from __future__ import annotations

import asyncio

from apps.server.src.services.stream_service import StreamService


def test_same_idempotency_key_returns_existing_message() -> None:
    service = StreamService()

    async def _run() -> None:
        first = await service.publish("s1", "event", {"event_type": "dice_roll", "idempotency_key": "idem:1"})
        second = await service.publish("s1", "event", {"event_type": "dice_roll", "idempotency_key": "idem:1", "dice": [6]})

        assert first.seq == second.seq
        assert len(await service.snapshot("s1")) == 1

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

        assert len(await service.snapshot("s1")) == 2

    asyncio.run(_run())
