"""Unit tests for the Ollama LLM backend and LLM domain models."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    STTSettings,
    StorageSettings,
)
from taskify.llm import MatrixQuadrant, OllamaBackend, TaskItem, get_llm_backend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def llm_settings() -> LLMSettings:
    return LLMSettings(
        backend="ollama",
        ollama_host="http://localhost:11434",
        ollama_model="phi4-mini",
        extraction_interval_s=300,
    )


@pytest.fixture
def dummy_settings(llm_settings: LLMSettings) -> Settings:
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
        llm=llm_settings,
        storage=StorageSettings(data_dir=None, log_dir=None),  # type: ignore
        logging=LoggingSettings(level="INFO", debug_llm=False),
    )


@pytest.fixture
def backend(llm_settings: LLMSettings) -> OllamaBackend:
    return OllamaBackend(llm_settings)


# ---------------------------------------------------------------------------
# MatrixQuadrant tests
# ---------------------------------------------------------------------------

class TestMatrixQuadrant:
    def test_valid_from_string(self) -> None:
        assert MatrixQuadrant.from_string("do_first") == MatrixQuadrant.DO_FIRST
        assert MatrixQuadrant.from_string("SCHEDULE") == MatrixQuadrant.SCHEDULE
        assert MatrixQuadrant.from_string("delegate") == MatrixQuadrant.DELEGATE
        assert MatrixQuadrant.from_string("eliminate") == MatrixQuadrant.ELIMINATE

    def test_case_insensitive_and_hyphen(self) -> None:
        assert MatrixQuadrant.from_string("DO-FIRST") == MatrixQuadrant.DO_FIRST
        assert MatrixQuadrant.from_string("  Schedule  ") == MatrixQuadrant.SCHEDULE

    def test_invalid_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown quadrant"):
            MatrixQuadrant.from_string("unknown-value")


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestOllamaAvailability:
    def test_available_when_200(self, backend: OllamaBackend) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(backend._client, "get", return_value=mock_resp):
            assert backend.is_available is True

    def test_unavailable_when_500(self, backend: OllamaBackend) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch.object(backend._client, "get", return_value=mock_resp):
            assert backend.is_available is False

    def test_unavailable_on_connection_error(self, backend: OllamaBackend) -> None:
        with patch.object(
            backend._client,
            "get",
            side_effect=httpx.ConnectError("refused"),
        ):
            assert backend.is_available is False


# ---------------------------------------------------------------------------
# extract_tasks
# ---------------------------------------------------------------------------

class TestExtractTasks:
    def _mock_generate(
        self, backend: OllamaBackend, response_body: object
    ) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(response_body)}
        return patch.object(backend._client, "post", return_value=mock_resp)

    def test_extracts_single_task(self, backend: OllamaBackend) -> None:
        payload = [
            {
                "title": "Buy groceries",
                "notes": "Oat milk and bread",
                "due_date": "2099-01-10",
                "quadrant": "schedule",
                "confidence": 0.95,
            }
        ]
        with self._mock_generate(backend, payload):
            tasks = backend.extract_tasks("I need to buy groceries tomorrow.")

        assert len(tasks) == 1
        assert tasks[0].title == "Buy groceries"
        assert tasks[0].quadrant == MatrixQuadrant.SCHEDULE
        assert tasks[0].confidence == 0.95

    def test_extracts_multiple_tasks(self, backend: OllamaBackend) -> None:
        payload = [
            {"title": "Task A", "quadrant": "do_first", "confidence": 0.9},
            {"title": "Task B", "quadrant": "eliminate", "confidence": 0.5},
        ]
        with self._mock_generate(backend, payload):
            tasks = backend.extract_tasks("Do task A urgently. Task B is low priority.")

        assert len(tasks) == 2
        assert tasks[0].quadrant == MatrixQuadrant.DO_FIRST
        assert tasks[1].quadrant == MatrixQuadrant.ELIMINATE

    def test_empty_array_returns_empty_list(self, backend: OllamaBackend) -> None:
        with self._mock_generate(backend, []):
            tasks = backend.extract_tasks("Nothing to do here.")
        assert tasks == []

    def test_empty_transcript_skips_api(self, backend: OllamaBackend) -> None:
        with patch.object(backend._client, "post") as mock_post:
            tasks = backend.extract_tasks("   ")
        mock_post.assert_not_called()
        assert tasks == []

    def test_malformed_json_returns_empty_list(self, backend: OllamaBackend) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "not valid json {{}"}
        with patch.object(backend._client, "post", return_value=mock_resp):
            tasks = backend.extract_tasks("Some transcript.")
        assert tasks == []

    def test_missing_title_skips_entry(self, backend: OllamaBackend) -> None:
        payload = [
            {"notes": "No title here", "quadrant": "schedule"},
        ]
        with self._mock_generate(backend, payload):
            tasks = backend.extract_tasks("transcript")
        assert tasks == []

    def test_unknown_quadrant_defaults_to_schedule(
        self, backend: OllamaBackend
    ) -> None:
        payload = [{"title": "Mystery task", "quadrant": "unknown-thing"}]
        with self._mock_generate(backend, payload):
            tasks = backend.extract_tasks("mystery")
        assert tasks[0].quadrant == MatrixQuadrant.SCHEDULE

    def test_retry_on_http_error(self, backend: OllamaBackend) -> None:
        """Backend should retry on 5xx and eventually return empty list."""
        backend._retries = 2
        error_resp = MagicMock()
        error_resp.status_code = 503
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=error_resp
        )
        with patch.object(backend._client, "post", return_value=error_resp):
            with patch("taskify.llm.ollama_backend.time.sleep"):
                tasks = backend.extract_tasks("retry test")
        assert tasks == []

    def test_retry_on_connection_error(self, backend: OllamaBackend) -> None:
        backend._retries = 2
        with patch.object(
            backend._client,
            "post",
            side_effect=httpx.ConnectError("refused"),
        ):
            with patch("taskify.llm.ollama_backend.time.sleep"):
                tasks = backend.extract_tasks("connection failure")
        assert tasks == []


# ---------------------------------------------------------------------------
# classify_matrix
# ---------------------------------------------------------------------------

class TestClassifyMatrix:
    def _mock_post(
        self, backend: OllamaBackend, quadrant_str: str
    ) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "response": json.dumps({"quadrant": quadrant_str})
        }
        return patch.object(backend._client, "post", return_value=mock_resp)

    def test_classifies_do_first(self, backend: OllamaBackend) -> None:
        task = TaskItem(title="Fix production outage", notes="Critical issue")
        with self._mock_post(backend, "do_first"):
            result = backend.classify_matrix(task)
        assert result == MatrixQuadrant.DO_FIRST

    def test_classifies_delegate(self, backend: OllamaBackend) -> None:
        task = TaskItem(title="Schedule a meeting", notes="")
        with self._mock_post(backend, "delegate"):
            result = backend.classify_matrix(task)
        assert result == MatrixQuadrant.DELEGATE

    def test_invalid_quadrant_defaults_to_schedule(
        self, backend: OllamaBackend
    ) -> None:
        task = TaskItem(title="Ambiguous task")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": '{"quadrant": "unknown"}'}
        with patch.object(backend._client, "post", return_value=mock_resp):
            result = backend.classify_matrix(task)
        assert result == MatrixQuadrant.SCHEDULE


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestLLMFactory:
    def test_returns_ollama_backend(self, dummy_settings: Settings) -> None:
        with patch.object(OllamaBackend, "is_available", new_callable=lambda: property(lambda self: True)):
            backend = get_llm_backend(dummy_settings)
        assert isinstance(backend, OllamaBackend)

    def test_nlp_backend_returns_nlp_instance(self, dummy_settings: Settings) -> None:
        from taskify.llm import NLPBackend

        dummy_settings.llm.backend = "nlp"
        backend = get_llm_backend(dummy_settings)
        assert isinstance(backend, NLPBackend)

    def test_unknown_backend_raises_value_error(
        self, dummy_settings: Settings
    ) -> None:
        dummy_settings.llm.backend = "gpt-99"
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            get_llm_backend(dummy_settings)
