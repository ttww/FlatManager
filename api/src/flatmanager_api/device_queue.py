"""
Per-device async command notification queue.

Provides lightweight signaling to wake waiting devices when commands arrive,
without storing command payloads (DB remains source of truth).
"""

import asyncio
from typing import Dict


class DeviceQueueManager:
    """
    Manages per-device async Event instances for wake-up signaling.

    When a command is created for a device, notify() signals all waiters.
    When a device calls wait(), it blocks on the Event until signaled or timeout.

    Thread-safe and coroutine-safe via asyncio.Event.
    """

    def __init__(self) -> None:
        self._events: Dict[int, asyncio.Event] = {}

    def notify(self, device_id: int) -> None:
        """Signal all waiters for this device (create Event if needed)."""
        if device_id not in self._events:
            self._events[device_id] = asyncio.Event()
        self._events[device_id].set()

    async def wait_for_signal(self, device_id: int, timeout_seconds: float) -> bool:
        """
        Wait for a signal for this device with timeout.

        Returns True if signaled, False if timeout reached.
        """
        if device_id not in self._events:
            self._events[device_id] = asyncio.Event()

        event = self._events[device_id]

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            # Reset for next waiter(s)
            event.clear()

    def cleanup(self, device_id: int) -> None:
        """Remove Event for device (optional, for memory cleanup on device deletion)."""
        self._events.pop(device_id, None)


# Global instance
_queue_manager: DeviceQueueManager | None = None


def get_queue_manager() -> DeviceQueueManager:
    """Lazy initialization of global queue manager."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = DeviceQueueManager()
    return _queue_manager
