"""Integration test suite executing the full audio-to-task persistence and classification pipeline."""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    STTSettings,
    StorageSettings,
)
from taskify.llm.nlp_backend import NLPBackend
from taskify.pipeline.scheduler import EventBus, ExtractionScheduler
from taskify.storage.database import DatabaseManager
from taskify.storage.models import TranscriptSegment
from taskify.storage.transcript_writer import TranscriptWriter
from taskify.stt import VoskEngine

if TYPE_CHECKING:
    from taskify.stt.base import STTEngine

# Define 5 representative speech samples (transcripts)
EXPECTED_TRANSCRIPTS = [
    "I must immediately buy groceries today.",
    "We need to plan a strategic roadmap.",
    "I need to tell John to fix the website right now.",
    "I should maybe write a funny story eventually.",
    "We have to urgently write the report before noon.",
]

# Define expected classifications mapped from keywords/rules
EXPECTED_QUADRANTS = [
    "urgent_important",
    "important_not_urgent",
    "urgent_not_important",
    "neither",
    "urgent_important",
]


class MockKaldiRecognizer:
    """Mock Vosk recognizer returning representative sentences sequentially."""

    current_index = 0
    has_returned_for_current = False

    def __init__(self, model: MagicMock, rate: float) -> None:
        pass

    def AcceptWaveform(self, data: bytes) -> bool:
        return True

    def Result(self) -> str:
        if not MockKaldiRecognizer.has_returned_for_current:
            text = EXPECTED_TRANSCRIPTS[MockKaldiRecognizer.current_index]
            MockKaldiRecognizer.has_returned_for_current = True
            return json.dumps({"text": text})
        return json.dumps({"text": ""})

    def PartialResult(self) -> str:
        return '{"partial": ""}'

    def FinalResult(self) -> str:
        return json.dumps({"text": ""})


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Fixture returning settings pointing to temp directories."""
    return Settings(
        audio=AudioSettings(
            device="default",
            sample_rate=16000,
            chunk_duration_ms=200,
            silence_threshold=0.01,
            silence_duration_s=1.5,
        ),
        stt=STTSettings(
            engine="vosk",
            vosk_model="en-small",
            whisper_model="base",
            language="en",
        ),
        llm=LLMSettings(
            backend="nlp",
            ollama_host="http://localhost:11434",
            ollama_model="phi4-mini",
            extraction_interval_s=300,
        ),
        storage=StorageSettings(
            data_dir=tmp_path / "data",
            log_dir=tmp_path / "logs",
        ),
        logging=LoggingSettings(
            level="INFO",
            debug_llm=False,
        ),
    )


@pytest.fixture
def db(test_settings: Settings) -> Generator[DatabaseManager, None, None]:
    """Fixture returning an initialized DatabaseManager."""
    db_path = test_settings.storage.data_dir / "taskify.db"
    test_settings.storage.data_dir.mkdir(parents=True, exist_ok=True)
    manager = DatabaseManager(db_path)
    yield manager
    manager.close()


def create_dummy_wav(path: Path, frequency: int = 440, duration: float = 0.5, rate: int = 16000) -> None:
    """Write a valid mono 16-bit PCM WAV file filled with a sine wave."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        n_frames = int(duration * rate)
        for i in range(n_frames):
            val = int(32767.0 * math.sin(2.0 * math.pi * frequency * i / rate))
            wf.writeframes(struct.pack("<h", val))


def read_wav_chunks(path: Path, chunk_size_samples: int = 3200) -> list[np.ndarray]:
    """Read a WAV file and split it into float32 numpy array chunks."""
    with wave.open(str(path), "rb") as wf:
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        sig = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

        # Chunk the signal
        chunks: list[np.ndarray] = []
        for i in range(0, len(sig), chunk_size_samples):
            chunk = sig[i : i + chunk_size_samples]
            if len(chunk) < chunk_size_samples:
                # Pad zeros
                chunk = np.pad(chunk, (0, chunk_size_samples - len(chunk)))
            chunks.append(chunk)
        return chunks


@patch("vosk.Model")
@patch("vosk.KaldiRecognizer", new=MockKaldiRecognizer)
def test_full_audio_to_task_pipeline(
    mock_model: MagicMock,
    test_settings: Settings,
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Integration test verifying full audio chunk processing through to classified tasks."""
    # 1. Generate 5 unique WAV files to simulate recording inputs
    wav_paths: list[Path] = []
    for idx in range(5):
        wav_path = tmp_path / f"sample_{idx}.wav"
        create_dummy_wav(wav_path, frequency=300 + idx * 50)
        wav_paths.append(wav_path)

    # 2. Setup Vosk STT Engine with mock model directory
    model_dir = tmp_path / "vosk-model-small-en-us-0.15"
    model_dir.mkdir()

    engine = VoskEngine(test_settings)
    engine._model_root = tmp_path
    engine.initialize()

    # 3. Setup TranscriptWriter batch persistence
    writer = TranscriptWriter(db=db, log_dir=test_settings.storage.log_dir, flush_interval_s=0.1)
    writer.start()

    # Create the session first in the DB due to foreign key constraints
    session_id = "test-session-uuid-999"
    db.create_session(session_id, start_time=0.0)

    # 4. Process each WAV file through VoskEngine and write to TranscriptWriter
    for idx, path in enumerate(wav_paths):
        MockKaldiRecognizer.current_index = idx
        MockKaldiRecognizer.has_returned_for_current = False

        chunks = read_wav_chunks(path)

        # Transcribe chunks
        transcription = ""
        for chunk in chunks:
            text = engine.transcribe_chunk(chunk)
            if text:
                transcription += text + " "

        final_text = engine.flush()
        if final_text:
            transcription += final_text

        transcription = transcription.strip()

        # Write segment to TranscriptWriter
        segment = TranscriptSegment(
            session_id=session_id,
            text=transcription,
            confidence=0.9,
            start_time=float(idx * 2),
            end_time=float((idx + 1) * 2),
        )
        writer.write(segment)

    # Allow TranscriptWriter to flush batch to database
    writer.stop()

    # Verify transcripts are populated in database
    conn = db._conn
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transcripts;")
    count = cursor.fetchone()[0]
    assert count == 5

    # 5. Run task extraction cycle using the periodic scheduler pipeline
    nlp_backend = NLPBackend()
    event_bus = EventBus()
    scheduler = ExtractionScheduler(
        db=db,
        backend=nlp_backend,
        settings=test_settings,
        bus=event_bus,
    )

    # Manually execute the extraction cycle
    scheduler._run_extraction_cycle()

    # 6. Assert correct tasks creation and classifications
    cursor.execute("SELECT id, title FROM tasks ORDER BY id ASC;")
    db_tasks = cursor.fetchall()
    assert len(db_tasks) == 5

    # Match each task with its expected classification matrix quadrant
    for idx, (task_id, title) in enumerate(db_tasks):
        cursor.execute("SELECT quadrant FROM matrix_entries WHERE task_id = ?;", (task_id,))
        quadrant = cursor.fetchone()[0]

        # Verify classifications match expected quadrant rules
        assert quadrant == EXPECTED_QUADRANTS[idx]
        assert title.startswith(EXPECTED_TRANSCRIPTS[idx][:10])  # Title capitalization check
