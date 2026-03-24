# Smart Gallery for ComfyUI - Event System
# Persistent event log + in-memory pub/sub for SSE push to clients.

import json
import logging
import queue
import threading
import time
import uuid

from smartgallery.models import get_db_connection

logger = logging.getLogger(__name__)


class GalleryEvent:
    """A mutation event that gets logged and pushed to SSE clients."""
    __slots__ = ('id', 'timestamp', 'event_type', 'data', 'source')

    def __init__(self, event_type: str, data: dict, source: str = 'user'):
        self.id = uuid.uuid4().hex
        self.timestamp = time.time()
        self.event_type = event_type
        self.data = data
        self.source = source

    def to_sse(self) -> str:
        """Format as an SSE message with named event type."""
        return f"id: {self.id}\nevent: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


class EventBus:
    """Thread-safe pub/sub for pushing events to SSE clients."""

    def __init__(self):
        self._subscribers: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> tuple[str, queue.Queue]:
        """Register a new SSE client. Returns (client_id, event_queue)."""
        client_id = uuid.uuid4().hex
        q = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers[client_id] = q
        logger.debug("SSE client connected: %s (%d active)", client_id[:8], len(self._subscribers))
        return client_id, q

    def unsubscribe(self, client_id: str):
        """Remove a disconnected client."""
        with self._lock:
            self._subscribers.pop(client_id, None)
        logger.debug("SSE client disconnected: %s", client_id[:8])

    def publish(self, event: GalleryEvent):
        """Push event to all subscribers. Non-blocking; drops client if queue full."""
        with self._lock:
            dead = []
            for cid, q in self._subscribers.items():
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(cid)
            for cid in dead:
                self._subscribers.pop(cid, None)
                logger.warning("SSE client %s dropped (queue full)", cid[:8])

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# Module-level singleton
event_bus = EventBus()


def publish_event(event_type: str, data: dict, source: str = 'user'):
    """Log a mutation event and push to connected SSE clients.

    Called from route handlers after successful DB commit.
    Safe to call from any thread (uses thread-local DB connection).
    """
    event = GalleryEvent(event_type, data, source)

    # 1. Persist to event_log table
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO event_log (id, timestamp, event_type, data, source) VALUES (?, ?, ?, ?, ?)",
                (event.id, event.timestamp, event.event_type, json.dumps(event.data), event.source)
            )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to persist event %s: %s", event_type, e)

    # 2. Push to live SSE subscribers
    event_bus.publish(event)

    logger.info("Event: %s %s", event_type, json.dumps(data)[:200])
