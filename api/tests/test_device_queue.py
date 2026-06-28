import asyncio

import pytest

from flatmanager_api.device_queue import DeviceQueueManager


@pytest.mark.asyncio
async def test_notify_all_wakes_waiters() -> None:
    queue = DeviceQueueManager()

    waiter_one = asyncio.create_task(queue.wait_for_signal(1, timeout_seconds=5))
    waiter_two = asyncio.create_task(queue.wait_for_signal(2, timeout_seconds=5))

    await asyncio.sleep(0.01)
    queue.notify_all()

    result_one, result_two = await asyncio.gather(waiter_one, waiter_two)

    assert result_one is True
    assert result_two is True
