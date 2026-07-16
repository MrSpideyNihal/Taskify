"""Unit tests for TranscriptWriter — batch flushing and daily log rotation."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from taskify.storage.models import TranscriptSegment
from taskify.storage.transcript_writer import TranscriptWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seg(
    text: str = "Buy oat milk",
    session_id: str = "sess-001",
    start: float = 1_700_000_000.0,
    end: float = 1_700_000_005.0,
    confidence: float = 0.92,
) -> TranscriptSegment:
    return TranscriptSegment(
        session_id=session_id,
        text=text,
        confidence=confidence,
        start_time=start,
        end_time=end,
    )


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a mock DatabaseManager that records calls."""
    db = MagicMock()
    db.insert_transcripts = MagicMock()
    return db


@pytest.fixture
def writer(mock_db: MagicMock, tmp_path: Path) -> TranscriptWriter:
    """Return a started TranscriptWriter writing logs to tmp_path."""
    w = TranscriptWriter(
        db=mock_db,
        log_dir=tmp_path,
        batch_size=10,
        flush_interval_s=0.5,
    )
    w.start()
    yield w
    w.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranscriptWriterBatching:
    """Verify that segments are persisted via DatabaseManager."""

    def test_single_segment_is_persisted(
        self, writer: TranscriptWriter, mock_db: MagicMock
    ) -> None:
        seg = _seg("Pick up dry cleaning")
        writer.write(seg)
        writer.flush()

        mock_db.insert_transcripts.assert_called_once()
        args, _ = mock_db.insert_transcripts.call_args
        assert args[0][0].text == "Pick up dry cleaning"

    def test_multiple_segments_batched(
        self, writer: TranscriptWriter, mock_db: MagicMock
    ) -> None:
        for i in range(5):
            writer.write(_seg(f"Task number {i}"))
        writer.flush()

        # May be in one or more calls; total segments must equal 5
        total = sum(
            len(call.args[0])
            for call in mock_db.insert_transcripts.call_args_list
        )
        assert total == 5

    def test_write_raises_before_start(self, mock_db: MagicMock) -> None:
        w = TranscriptWriter(db=mock_db, log_dir=Path("."), flush_interval_s=0.5)
        with pytest.raises(RuntimeError, match="start()"):
            w.write(_seg())
        # Thread was never started — just mark stopped so stop() is a no-op
        w._stopped = True

    def test_write_raises_after_stop(
        self, writer: TranscriptWriter
    ) -> None:
        writer.stop()
        with pytest.raises(RuntimeError, match="stopped"):
            writer.write(_seg())


class TestDailyLogRotation:
    """Verify Markdown and JSON Lines files are written and rotate correctly."""

    def test_markdown_file_created(
        self, writer: TranscriptWriter, tmp_path: Path
    ) -> None:
        writer.write(_seg("Call the dentist"))
        writer.flush()

        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "Call the dentist" in content

    def test_json_file_created(
        self, writer: TranscriptWriter, tmp_path: Path
    ) -> None:
        writer.write(_seg("Book a flight"))
        writer.flush()

        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 1
        lines = json_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["text"] == "Book a flight"
        assert "session_id" in record
        assert "logged_at" in record

    def test_multiple_segments_all_logged(
        self, writer: TranscriptWriter, tmp_path: Path
    ) -> None:
        texts = ["Task A", "Task B", "Task C"]
        for t in texts:
            writer.write(_seg(t))
        writer.flush()

        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 1
        lines = json_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        logged_texts = [json.loads(l)["text"] for l in lines]
        assert set(logged_texts) == set(texts)

    def test_log_rotates_at_midnight(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        """Simulate a date change and verify a new log file is created."""
        w = TranscriptWriter(
            db=mock_db, log_dir=tmp_path, flush_interval_s=0.2
        )
        w.start()

        # Patch _current_date_str to return "day-one" first, then "day-two"
        call_count = {"n": 0}

        def fake_date() -> str:
            call_count["n"] += 1
            # First segment gets date "2099-01-01", second gets "2099-01-02"
            return "2099-01-01" if call_count["n"] <= 1 else "2099-01-02"

        w._current_date_str = fake_date  # type: ignore[method-assign]

        w.write(_seg("Morning standup"))
        w.flush()
        w.write(_seg("Evening review"))
        w.flush()
        w.stop()

        md_files = sorted(tmp_path.glob("*.md"))
        json_files = sorted(tmp_path.glob("*.json"))
        assert len(md_files) == 2
        assert len(json_files) == 2

    def test_markdown_header_written_once(
        self, writer: TranscriptWriter, tmp_path: Path
    ) -> None:
        for _ in range(3):
            writer.write(_seg())
        writer.flush()

        md_file = next(iter(tmp_path.glob("*.md")))
        content = md_file.read_text(encoding="utf-8")
        # Header should appear exactly once
        assert content.count("# Taskify Transcript Log") == 1


class TestGracefulShutdown:
    """Verify that stop() drains the queue before exiting."""

    def test_stop_drains_all_segments(
        self, mock_db: MagicMock, tmp_path: Path
    ) -> None:
        w = TranscriptWriter(
            db=mock_db, log_dir=tmp_path, flush_interval_s=60.0
        )
        w.start()

        for i in range(15):
            w.write(_seg(f"Segment {i}"))

        w.stop()  # Must drain before returning

        total = sum(
            len(call.args[0])
            for call in mock_db.insert_transcripts.call_args_list
        )
        assert total == 15
