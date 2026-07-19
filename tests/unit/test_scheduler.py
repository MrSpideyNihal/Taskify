"""Unit tests for ExtractionScheduler and EventBus."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from taskify.llm.models import MatrixQuadrant, TaskItem
from taskify.pipeline.scheduler import (
    EVENT_TASKS_UPDATED,
    EVENT_TRIGGER_EXTRACTION,
    EventBus,
    ExtractionScheduler,
)
from taskify.storage.models import TranscriptSegment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    text: str = "Buy milk today",
    seg_id: int = 1,
    session_id: str = "sess-001",
) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        session_id=session_id,
        text=text,
        confidence=0.9,
        start_time=1_700_000_000.0,
        end_time=1_700_000_005.0,
    )


def _make_task(title: str = "Buy milk today") -> TaskItem:
    return TaskItem(
        title=title,
        quadrant=MatrixQuadrant.SCHEDULE,
    )


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.get_unprocessed_transcripts.return_value = []
    db.mark_transcripts_processed = MagicMock()
    db.create_task = MagicMock(return_value=(MagicMock(), MagicMock()))
    return db


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock()
    backend.extract_tasks.return_value = []
    return backend


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.llm.extraction_interval_s = 60
    return settings


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def scheduler(
    mock_db: MagicMock,
    mock_backend: MagicMock,
    mock_settings: MagicMock,
    bus: EventBus,
) -> ExtractionScheduler:
    return ExtractionScheduler(
        db=mock_db,
        backend=mock_backend,
        settings=mock_settings,
        bus=bus,
        interval_s=999.0,  # effectively never fires automatically
    )


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class TestEventBus:
    def test_subscribe_and_emit(self, bus: EventBus) -> None:
        received: list[object] = []
        bus.subscribe("test_event", received.append)
        bus.emit("test_event", {"key": "value"})
        assert received == [{"key": "value"}]

    def test_multiple_listeners(self, bus: EventBus) -> None:
        results: list[int] = []
        bus.subscribe("ev", lambda d: results.append(1))
        bus.subscribe("ev", lambda d: results.append(2))
        bus.emit("ev")
        assert sorted(results) == [1, 2]

    def test_emit_unknown_event_is_noop(self, bus: EventBus) -> None:
        bus.emit("no_such_event")  # should not raise

    def test_unsubscribe(self, bus: EventBus) -> None:
        received: list[object] = []
        cb = received.append
        bus.subscribe("ev", cb)
        bus.unsubscribe("ev", cb)
        bus.emit("ev", "data")
        assert received == []

    def test_listener_exception_does_not_propagate(self, bus: EventBus) -> None:
        def bad_cb(data: object) -> None:
            raise RuntimeError("listener boom")

        bus.subscribe("ev", bad_cb)
        bus.emit("ev")  # must not raise

    def test_data_none_default(self, bus: EventBus) -> None:
        received: list[object] = []
        bus.subscribe("ev", received.append)
        bus.emit("ev")
        assert received == [None]


# ---------------------------------------------------------------------------
# ExtractionScheduler — cycle logic
# ---------------------------------------------------------------------------


class TestExtractionCycle:
    def test_no_segments_skips_backend(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
    ) -> None:
        mock_db.get_unprocessed_transcripts.return_value = []
        scheduler._run_extraction_cycle()
        mock_backend.extract_tasks.assert_not_called()

    def test_segments_are_extracted_and_persisted(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
        bus: EventBus,
    ) -> None:
        seg = _make_segment("Call the dentist today")
        mock_db.get_unprocessed_transcripts.return_value = [seg]
        task = _make_task("Call the dentist today")
        mock_backend.extract_tasks.return_value = [task]

        events: list[object] = []
        bus.subscribe(EVENT_TASKS_UPDATED, events.append)

        scheduler._run_extraction_cycle()

        mock_backend.extract_tasks.assert_called_once_with("Call the dentist today")
        mock_db.create_task.assert_called_once_with(
            title="Call the dentist today",
            notes="",
            due_date="",
            quadrant=MatrixQuadrant.SCHEDULE.value,
        )
        mock_db.mark_transcripts_processed.assert_called_once_with([1])
        assert len(events) == 1
        assert events[0]["extracted"] == 1  # type: ignore[index]

    def test_multiple_segments_all_processed(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
    ) -> None:
        segs = [_make_segment(f"Task {i}", seg_id=i) for i in range(1, 4)]
        mock_db.get_unprocessed_transcripts.return_value = segs
        mock_backend.extract_tasks.return_value = [_make_task()]

        scheduler._run_extraction_cycle()

        assert mock_backend.extract_tasks.call_count == 3
        mock_db.mark_transcripts_processed.assert_called_once_with([1, 2, 3])

    def test_backend_error_skips_segment_continues(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
    ) -> None:
        segs = [_make_segment("Good task", 1), _make_segment("Bad task", 2)]
        mock_db.get_unprocessed_transcripts.return_value = segs

        # First call succeeds, second raises
        mock_backend.extract_tasks.side_effect = [
            [_make_task("Good task")],
            RuntimeError("backend exploded"),
        ]

        scheduler._run_extraction_cycle()

        # Good segment is still persisted and marked
        mock_db.create_task.assert_called_once()
        mock_db.mark_transcripts_processed.assert_called_once_with([1])

    def test_no_event_emitted_when_no_tasks_extracted(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
        bus: EventBus,
    ) -> None:
        seg = _make_segment("hmm interesting")
        mock_db.get_unprocessed_transcripts.return_value = [seg]
        mock_backend.extract_tasks.return_value = []

        events: list[object] = []
        bus.subscribe(EVENT_TASKS_UPDATED, events.append)

        scheduler._run_extraction_cycle()

        assert events == []

    def test_db_fetch_error_handled_gracefully(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
    ) -> None:
        mock_db.get_unprocessed_transcripts.side_effect = RuntimeError("db gone")
        scheduler._run_extraction_cycle()  # must not raise
        mock_backend.extract_tasks.assert_not_called()

    def test_manual_trigger_extraction(
        self,
        scheduler: ExtractionScheduler,
        mock_db: MagicMock,
        mock_backend: MagicMock,
        bus: EventBus,
    ) -> None:
        seg = _make_segment("Immediate task", 1)
        mock_db.get_unprocessed_transcripts.return_value = [seg]
        mock_backend.extract_tasks.return_value = [_make_task("Immediate task")]

        # Emit the manual trigger event
        bus.emit(EVENT_TRIGGER_EXTRACTION)

        # Give the background thread a short moment to execute
        time.sleep(0.1)

        # Extraction should be performed immediately
        mock_db.get_unprocessed_transcripts.assert_called()
        mock_backend.extract_tasks.assert_called_with("Immediate task")
        mock_db.create_task.assert_called_once()


# ---------------------------------------------------------------------------
# ExtractionScheduler — lifecycle
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    def test_is_running_false_before_start(
        self, scheduler: ExtractionScheduler
    ) -> None:
        assert scheduler.is_running is False

    def test_is_running_true_after_start(self, scheduler: ExtractionScheduler) -> None:
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()

    def test_is_running_false_after_stop(self, scheduler: ExtractionScheduler) -> None:
        scheduler.start()
        scheduler.stop()
        assert scheduler.is_running is False

    def test_start_is_idempotent(self, scheduler: ExtractionScheduler) -> None:
        scheduler.start()
        scheduler.start()  # second call must not spawn extra timers
        assert scheduler.is_running is True
        scheduler.stop()

    def test_stop_before_start_is_safe(self, scheduler: ExtractionScheduler) -> None:
        scheduler.stop()  # must not raise

    def test_timer_fires_and_extracts(
        self,
        mock_db: MagicMock,
        mock_backend: MagicMock,
        mock_settings: MagicMock,
        bus: EventBus,
    ) -> None:
        """Verify a real timer fires within a short interval and calls extraction."""
        seg = _make_segment("Buy coffee")
        mock_db.get_unprocessed_transcripts.return_value = [seg]
        mock_backend.extract_tasks.return_value = [_make_task("Buy coffee")]

        sched = ExtractionScheduler(
            db=mock_db,
            backend=mock_backend,
            settings=mock_settings,
            bus=bus,
            interval_s=0.1,  # fire quickly
        )
        sched.start()
        time.sleep(0.4)  # allow at least one tick
        sched.stop()

        assert mock_backend.extract_tasks.call_count >= 1

    def test_stop_drains_in_progress_cycle(
        self,
        mock_db: MagicMock,
        mock_backend: MagicMock,
        mock_settings: MagicMock,
        bus: EventBus,
    ) -> None:
        """stop() must wait for a running cycle to complete."""
        cycle_completed = threading.Event()
        original_cycle = ExtractionScheduler._run_extraction_cycle

        def slow_cycle(self: ExtractionScheduler) -> None:
            time.sleep(0.15)
            original_cycle(self)
            cycle_completed.set()

        sched = ExtractionScheduler(
            db=mock_db,
            backend=mock_backend,
            settings=mock_settings,
            bus=bus,
            interval_s=0.05,
        )
        with patch.object(ExtractionScheduler, "_run_extraction_cycle", slow_cycle):
            sched.start()
            time.sleep(0.1)  # let tick fire and enter slow_cycle
            sched.stop()

        # After stop() returns, the cycle must have finished
        assert cycle_completed.is_set()
