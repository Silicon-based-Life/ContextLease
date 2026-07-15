from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from threading import Condition, RLock
from typing import Iterable

from .models import ArenaSnapshot, TraceEvent, to_public_dict


class ObservationStore:
    """Bounded, thread-safe telemetry store. Prompt content is never stored."""

    def __init__(self, max_events_per_arena: int = 10_000) -> None:
        if max_events_per_arena <= 0:
            raise ValueError("max_events_per_arena must be positive")
        self._max_events = max_events_per_arena
        self._snapshots: dict[str, ArenaSnapshot] = {}
        self._events: dict[str, deque[TraceEvent]] = defaultdict(
            lambda: deque(maxlen=self._max_events)
        )
        self._dropped: dict[str, int] = defaultdict(int)
        self._lock = RLock()
        self._condition = Condition(self._lock)

    def publish_snapshot(self, snapshot: ArenaSnapshot) -> None:
        with self._condition:
            self._snapshots[snapshot.arena_id] = snapshot
            self._condition.notify_all()

    def publish_event(self, event: TraceEvent) -> None:
        with self._condition:
            queue = self._events[event.arena_id]
            if len(queue) == queue.maxlen:
                self._dropped[event.arena_id] += 1
            queue.append(event)
            self._condition.notify_all()

    def publish_many(self, events: Iterable[TraceEvent]) -> None:
        for event in events:
            self.publish_event(event)

    def list_arenas(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "arena_id": snapshot.arena_id,
                    "instance_id": snapshot.instance_id,
                    "snapshot_seq": snapshot.snapshot_seq,
                    "captured_at": snapshot.captured_at.isoformat(),
                    "model_profile_id": snapshot.model_profile_id,
                    "used_tokens": snapshot.used_tokens,
                    "input_budget_tokens": snapshot.input_budget_tokens,
                    "pressure": snapshot.pressure.value,
                }
                for snapshot in sorted(self._snapshots.values(), key=lambda item: item.arena_id)
            ]

    def get_snapshot(self, arena_id: str) -> ArenaSnapshot | None:
        with self._lock:
            snapshot = self._snapshots.get(arena_id)
            if snapshot is None:
                return None
            dropped = self._dropped.get(arena_id, 0)
            return replace(snapshot, health={**snapshot.health, "events_dropped": dropped})

    def events_after(self, arena_id: str, after_seq: int = 0, limit: int = 1000) -> list[TraceEvent]:
        safe_limit = max(1, min(limit, 10_000))
        with self._lock:
            return [event for event in self._events.get(arena_id, ()) if event.seq > after_seq][
                :safe_limit
            ]

    def minimum_event_seq(self, arena_id: str) -> int | None:
        with self._lock:
            events = self._events.get(arena_id)
            return events[0].seq if events else None

    def wait_for_events(
        self, arena_id: str, after_seq: int, timeout: float = 15.0
    ) -> list[TraceEvent]:
        with self._condition:
            ready = self.events_after(arena_id, after_seq)
            if ready:
                return ready
            self._condition.wait(timeout=timeout)
            return self.events_after(arena_id, after_seq)

    def public_snapshot(self, arena_id: str) -> dict | None:
        snapshot = self.get_snapshot(arena_id)
        return to_public_dict(snapshot) if snapshot else None
