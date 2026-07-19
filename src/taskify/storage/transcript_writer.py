"""Background transcript writer with SQLite persistence and daily rotating log files."""

import json
import queue
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from taskify.config import get_default_paths
from taskify.storage.database import DatabaseManager
from taskify.storage.models import TranscriptSegment

# Sentinel object to signal background thread shutdown
_STOP_SENTINEL = object()


class TranscriptWriter:
    """Thread-safe, background transcript persistence engine.

    Accepts :class:`TranscriptSegment` objects and asynchronously:
    - Batch-inserts them into the ``transcripts`` SQLite table via
      :class:`~taskify.storage.database.DatabaseManager`.
    - Appends formatted entries to a daily-rotating Markdown log file
      (``YYYY-MM-DD.md``) and a JSON Lines log file (``YYYY-MM-DD.json``).

    Log files are written to ``~/.local/share/taskify/logs/`` and rotate
    automatically at midnight without requiring a restart.

    Usage::

        writer = TranscriptWriter(db)
        writer.start()
        writer.write(segment)
        writer.flush()   # blocks until queue is drained
        writer.stop()    # graceful shutdown, drains queue first
    """

    def __init__(
        self,
        db: DatabaseManager,
        log_dir: Path | None = None,
        batch_size: int = 20,
        flush_interval_s: float = 5.0,
    ) -> None:
        """Initialise the writer.

        Args:
            db (DatabaseManager): Open database manager instance.
            log_dir (Path, optional): Override for the log directory.
                Defaults to ``~/.local/share/taskify/logs/``.
            batch_size (int): Maximum segments flushed per write cycle.
            flush_interval_s (float): Seconds between automatic flush cycles.
        """
        self._db = db

        _, data_dir = get_default_paths()
        self._log_dir: Path = log_dir if log_dir is not None else data_dir / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_s

        # Unbounded queue; caller is never blocked on write().
        # Each item placed here increments the unfinished-tasks counter.
        # task_done() is called only after the item has been fully persisted
        # so that flush() / queue.join() returns only when writes are complete.
        self._queue: queue.Queue[TranscriptSegment | object] = queue.Queue()

        # Background worker thread
        self._thread = threading.Thread(
            target=self._worker,
            name="TranscriptWriter",
            daemon=True,
        )
        self._started = False
        self._stopped = False

        # Lock protecting log file handles (rotated at midnight)
        self._log_lock = threading.Lock()
        self._current_log_date: str = ""
        self._md_file: Path | None = None
        self._json_file: Path | None = None

        # Register signal handlers so flush is called on SIGTERM / SIGINT
        self._register_signal_handlers()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background writer thread."""
        if self._started:
            return
        self._started = True
        self._thread.start()

    def write(self, segment: TranscriptSegment) -> None:
        """Enqueue a segment for asynchronous persistence.

        This method is non-blocking; the segment is placed on an internal
        queue and written by the background thread.

        Args:
            segment (TranscriptSegment): Transcribed speech segment.

        Raises:
            RuntimeError: If called before :meth:`start` or after :meth:`stop`.
        """
        if not self._started:
            raise RuntimeError("TranscriptWriter.start() must be called first.")
        if self._stopped:
            raise RuntimeError("TranscriptWriter has already been stopped.")
        self._queue.put(segment)

    def flush(self) -> None:
        """Block until all enqueued segments have been written.

        Safe to call from any thread. Returns once the queue is empty and
        all pending writes have fully completed (SQLite + log files).
        """
        self._queue.join()

    def stop(self) -> None:
        """Drain the queue and stop the background thread.

        Idempotent — calling multiple times is safe.
        """
        if self._stopped:
            return
        self._stopped = True
        if self._started:
            self._queue.put(_STOP_SENTINEL)
            self._thread.join(timeout=15)

    # ------------------------------------------------------------------
    # Internal: background thread
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """Background thread: dequeues and persists segments in batches.

        Design note: ``task_done()`` is called *after* the item has been
        fully persisted (inside ``_persist_batch``), not immediately after
        ``get()``.  This ensures ``queue.join()`` / ``flush()`` returns only
        once all I/O has completed.
        """
        pending: list[TranscriptSegment] = []
        last_flush = time.monotonic()

        while True:
            elapsed = time.monotonic() - last_flush
            timeout = max(0.0, self._flush_interval_s - elapsed)

            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                # Interval elapsed with no new item — flush whatever we have
                if pending:
                    self._persist_batch(pending)
                    pending = []
                last_flush = time.monotonic()
                continue

            # Sentinel → flush remainder and shut down
            if item is _STOP_SENTINEL:
                if pending:
                    self._persist_batch(pending)
                self._queue.task_done()
                break

            pending.append(item)  # type: ignore[arg-type]

            elapsed = time.monotonic() - last_flush
            should_flush = (
                len(pending) >= self._batch_size or elapsed >= self._flush_interval_s
            )
            if should_flush:
                self._persist_batch(pending)
                pending = []
                last_flush = time.monotonic()

    def _persist_batch(self, segments: list[TranscriptSegment]) -> None:
        """Persist a batch and call task_done() for each item.

        Args:
            segments (list[TranscriptSegment]): Segments to persist.
        """
        if not segments:
            return

        # 1. SQLite batch insert
        try:
            self._db.insert_transcripts(segments)
        except Exception as exc:  # noqa: BLE001
            print(f"[TranscriptWriter] SQLite error: {exc}")

        # 2. Daily log files (one entry per segment)
        for seg in segments:
            try:
                self._append_to_logs(seg)
            except Exception as exc:  # noqa: BLE001
                print(f"[TranscriptWriter] Log write error: {exc}")

        # Signal queue that every item in this batch is fully handled
        for _ in segments:
            self._queue.task_done()

    # ------------------------------------------------------------------
    # Internal: daily rotating log files
    # ------------------------------------------------------------------

    def _current_date_str(self) -> str:
        """Return today's date as ``YYYY-MM-DD`` in local time."""
        return datetime.now().strftime("%Y-%m-%d")

    def _rotate_if_needed(self, today: str) -> None:
        """Rotate log file paths when the calendar date has changed.

        Args:
            today (str): Today's date string (``YYYY-MM-DD``).
        """
        if today == self._current_log_date:
            return
        self._current_log_date = today
        self._md_file = self._log_dir / f"{today}.md"
        self._json_file = self._log_dir / f"{today}.json"

        # Write Markdown header if file is brand new
        if not self._md_file.exists():
            self._md_file.write_text(
                f"# Taskify Transcript Log — {today}\n\n",
                encoding="utf-8",
            )

    def _append_to_logs(self, seg: TranscriptSegment) -> None:
        """Append one segment to the Markdown and JSON Lines log files.

        Args:
            seg (TranscriptSegment): Segment to log.
        """
        today = self._current_date_str()
        with self._log_lock:
            self._rotate_if_needed(today)

            # Resolve human-readable timestamps
            start_dt = datetime.fromtimestamp(seg.start_time, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(seg.end_time, tz=timezone.utc)
            start_str = start_dt.strftime("%H:%M:%S")
            end_str = end_dt.strftime("%H:%M:%S")

            # --- Markdown entry ---
            if self._md_file is not None:
                md_entry = (
                    f"## [{start_str} \u2192 {end_str}] "
                    f"Session `{seg.session_id[:8]}\u2026`\n\n"
                    f"{seg.text.strip()}\n\n"
                    f"*confidence: {seg.confidence:.2f}*\n\n---\n\n"
                )
                with self._md_file.open("a", encoding="utf-8") as fh:
                    fh.write(md_entry)

            # --- JSON Lines entry ---
            if self._json_file is not None:
                json_entry = {
                    "session_id": seg.session_id,
                    "text": seg.text.strip(),
                    "confidence": round(seg.confidence, 4),
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "processed": seg.processed,
                    "logged_at": datetime.now(tz=timezone.utc).isoformat(),
                }
                with self._json_file.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(json_entry) + "\n")

    # ------------------------------------------------------------------
    # Internal: signal handling
    # ------------------------------------------------------------------

    def _register_signal_handlers(self) -> None:
        """Register SIGTERM and SIGINT handlers to flush before process exit."""

        def _handler(signum: int, frame: object) -> None:
            self.stop()

        try:
            signal.signal(signal.SIGTERM, _handler)
        except (OSError, ValueError):
            # Signals can only be registered from the main thread
            pass

        try:
            signal.signal(signal.SIGINT, _handler)
        except (OSError, ValueError):
            pass
