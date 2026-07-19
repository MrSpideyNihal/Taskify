"""Background task extraction scheduler.

Periodically pulls unprocessed transcript segments from SQLite, feeds them
through the configured LLM/NLP backend, and persists the resulting
:class:`~taskify.storage.models.TaskRecord` objects.  Emits events via a
lightweight :class:`EventBus` so the UI can refresh when new tasks arrive.

Architecture
------------
- Runs on a **dedicated daemon thread** — never blocks the GUI thread.
- Uses :mod:`threading.Timer` (stdlib only, no APScheduler dependency).
- Processes *only new* segments since the last run (``processed = 0``).
- Graceful shutdown: the ``stop()`` method signals the timer, waits for the
  current extraction cycle to finish, then returns.

Usage::

    bus   = EventBus()
    sched = ExtractionScheduler(db, backend, settings, bus)
    sched.start()          # begins periodic extraction
    ...
    sched.stop()           # drains current cycle and stops timer
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from taskify.config import Settings
from taskify.llm.base import LLMBackend
from taskify.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

# Event name emitted when new tasks are extracted and persisted
EVENT_TASKS_UPDATED = "tasks_updated"
# Event name emitted when configuration settings are updated
EVENT_SETTINGS_UPDATED = "settings_updated"
# Event name to trigger immediate manual extraction
EVENT_TRIGGER_EXTRACTION = "trigger_extraction"


class EventBus:
    """Minimal publish/subscribe bus for intra-process events.

    Listeners are called synchronously on the publisher's thread, so they
    must be fast (e.g. setting a flag or enqueuing a UI redraw request).

    Example::

        bus = EventBus()
        bus.subscribe("tasks_updated", lambda data: print("new tasks:", data))
        bus.emit("tasks_updated", {"count": 3})
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(self, event: str, callback: Callable[[object], None]) -> None:
        """Register *callback* to be invoked whenever *event* is emitted.

        Args:
            event (str): Event name string.
            callback: Callable accepting a single data argument.
        """
        with self._lock:
            self._listeners.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback: Callable[[object], None]) -> None:
        """Remove a previously registered callback.

        Args:
            event (str): Event name string.
            callback: The same callable reference passed to :meth:`subscribe`.
        """
        with self._lock:
            listeners = self._listeners.get(event, [])
            try:
                listeners.remove(callback)
            except ValueError:
                pass

    def emit(self, event: str, data: object = None) -> None:
        """Invoke all callbacks registered for *event*.

        Args:
            event (str): Event name string.
            data: Arbitrary payload passed to each callback.
        """
        with self._lock:
            listeners = list(self._listeners.get(event, []))

        for cb in listeners:
            try:
                cb(data)
            except Exception as exc:  # noqa: BLE001
                logger.error("EventBus listener error for '%s': %s", event, exc)


# ---------------------------------------------------------------------------
# ExtractionScheduler
# ---------------------------------------------------------------------------


class ExtractionScheduler:
    """Periodically extracts tasks from unprocessed transcript segments.

    Args:
        db (DatabaseManager): Open SQLite database manager.
        backend (LLMBackend): Configured extraction backend.
        settings (Settings): Application configuration (interval, etc.).
        bus (EventBus): Event bus for UI notification.
        interval_s (float, optional): Override extraction interval in seconds.
            Defaults to ``settings.llm.extraction_interval_s``.
    """

    def __init__(
        self,
        db: DatabaseManager,
        backend: LLMBackend,
        settings: Settings,
        bus: EventBus,
        interval_s: float | None = None,
    ) -> None:
        self._db = db
        self._backend = backend
        self._bus = bus
        self._interval_s = (
            float(interval_s)
            if interval_s is not None
            else float(settings.llm.extraction_interval_s)
        )
        self._settings = settings

        self._stop_event = threading.Event()
        self._running_lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._started = False

        # Subscribe to settings updates to allow live reload of extraction interval
        self._bus.subscribe(EVENT_SETTINGS_UPDATED, self._on_settings_updated)
        self._bus.subscribe(EVENT_TRIGGER_EXTRACTION, self._on_trigger_extraction)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic extraction cycle.

        Idempotent — calling multiple times is safe.
        """
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        logger.info("ExtractionScheduler started (interval=%.0fs).", self._interval_s)
        self._schedule_next()

    def stop(self) -> None:
        """Stop the scheduler and wait for any running cycle to finish.

        Idempotent — safe to call multiple times or before :meth:`start`.
        """
        self._stop_event.set()
        with self._running_lock:
            pass  # wait until current cycle exits the lock
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._started = False
        logger.info("ExtractionScheduler stopped.")

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is active.

        Returns:
            bool: Running state.
        """
        return self._started and not self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule_next(self) -> None:
        """Arm the next timer tick unless stop has been requested."""
        if self._stop_event.is_set():
            return
        self._timer = threading.Timer(self._interval_s, self._tick)
        self._timer.daemon = True
        self._timer.name = "ExtractionScheduler-tick"
        self._timer.start()

    def _tick(self) -> None:
        """Timer callback: run one extraction cycle then reschedule."""
        if self._stop_event.is_set():
            return

        with self._running_lock:
            if self._stop_event.is_set():
                return
            self._run_extraction_cycle()

        # Reschedule only if still running
        self._schedule_next()

    def _run_extraction_cycle(self) -> None:
        """Pull unprocessed segments, extract tasks, persist, and emit event.

        Handles errors per-segment so one bad transcript does not abort the
        entire batch.
        """
        try:
            segments = self._db.get_unprocessed_transcripts()
        except Exception as exc:  # noqa: BLE001
            logger.error("ExtractionScheduler: failed to fetch segments: %s", exc)
            return

        if not segments:
            logger.debug("ExtractionScheduler: no unprocessed segments found.")
            return

        logger.info("ExtractionScheduler: processing %d segment(s).", len(segments))

        extracted_count = 0
        processed_ids: list[int] = []

        for seg in segments:
            if self._stop_event.is_set():
                break  # Honour stop request mid-batch

            try:
                tasks = self._backend.extract_tasks(seg.text)
                for task in tasks:
                    self._db.create_task(
                        title=task.title,
                        notes=task.notes,
                        due_date=task.due_date,
                        quadrant=task.quadrant.value,
                    )
                    extracted_count += 1

                if seg.id is not None:
                    processed_ids.append(seg.id)

            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "ExtractionScheduler: error processing segment %s: %s",
                    seg.id,
                    exc,
                )

        # Mark processed in bulk
        if processed_ids:
            try:
                self._db.mark_transcripts_processed(processed_ids)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "ExtractionScheduler: failed to mark segments processed: %s",
                    exc,
                )

        if extracted_count > 0:
            logger.info(
                "ExtractionScheduler: extracted %d task(s) from %d segment(s).",
                extracted_count,
                len(processed_ids),
            )
            self._bus.emit(
                EVENT_TASKS_UPDATED,
                {"extracted": extracted_count, "segments": len(processed_ids)},
            )

    def _on_settings_updated(self, data: object) -> None:
        """Handle settings change event to dynamically update scheduler interval."""
        old_interval = self._interval_s
        self._interval_s = float(self._settings.llm.extraction_interval_s)
        logger.info(
            "ExtractionScheduler: updated interval from %.0fs to %.0fs "
            "based on settings change.",
            old_interval,
            self._interval_s,
        )

    def _on_trigger_extraction(self, data: object = None) -> None:
        """Start an immediate manual task extraction cycle in the background."""
        logger.info("ExtractionScheduler: received immediate manual trigger.")
        t = threading.Thread(
            target=self._run_extraction_cycle_with_lock,
            name="ExtractionScheduler-manual-trigger",
            daemon=True,
        )
        t.start()

    def _run_extraction_cycle_with_lock(self) -> None:
        with self._running_lock:
            if not self._stop_event.is_set():
                self._run_extraction_cycle()
