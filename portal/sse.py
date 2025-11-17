from __future__ import annotations

import queue
import threading
import time
from typing import Iterable


class AdminEventHub:
    def __init__(self) -> None:
        self._clients: set[queue.Queue[str]] = set()
        self._lock = threading.Lock()

    def register(self) -> queue.Queue[str]:
        channel: queue.Queue[str] = queue.Queue(maxsize=4)
        with self._lock:
            self._clients.add(channel)
        return channel

    def unregister(self, channel: queue.Queue[str]) -> None:
        with self._lock:
            if channel in self._clients:
                self._clients.remove(channel)
        while not channel.empty():
            try:
                channel.get_nowait()
            except queue.Empty:
                break

    def broadcast(self, event: str) -> None:
        with self._lock:
            clients = list(self._clients)
        for channel in clients:
            try:
                channel.put_nowait(event)
            except queue.Full:
                continue


def format_event(event_type: str, data: str) -> str:
    payload = data if data.strip() else "noop"
    return f"event: {event_type}\ndata: {payload}\n\n"


def heartbeat_event() -> str:
    return format_event("heartbeat", str(int(time.time())))


admin_event_hub = AdminEventHub()


__all__ = ["admin_event_hub", "format_event", "heartbeat_event"]
