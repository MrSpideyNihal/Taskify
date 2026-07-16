"""Ollama REST API backend for task extraction and matrix classification."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from taskify.config import LLMSettings
from taskify.llm.base import LLMBackend
from taskify.llm.models import MatrixQuadrant, TaskItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
You are a personal productivity assistant. Extract all actionable tasks \
from the following voice transcript.

Return a JSON array where each element is an object with these keys:
- "title": short imperative sentence (string, required)
- "notes": optional extra detail (string, may be empty)
- "due_date": ISO-8601 date string if mentioned, else empty string
- "quadrant": one of "do_first", "schedule", "delegate", "eliminate"
  based on urgency and importance signals in the text
- "confidence": float 0.0–1.0 reflecting extraction certainty

Rules:
- Output ONLY valid JSON — no markdown fences, no prose.
- If no tasks are found, return an empty array: []
- "do_first"  = urgent AND important (e.g. "deadline today", "critical")
- "schedule"  = important but not urgent (e.g. "someday", "plan to")
- "delegate"  = urgent but not important (e.g. "remind someone", "quick call")
- "eliminate" = neither urgent nor important

Transcript:
\"\"\"
{transcript}
\"\"\"
"""

_CLASSIFY_PROMPT = """\
Classify the following task into an Eisenhower Matrix quadrant.

Task title: {title}
Task notes: {notes}

Return ONLY a JSON object with a single key "quadrant" whose value is one of:
"do_first", "schedule", "delegate", "eliminate"

Example: {{"quadrant": "schedule"}}
"""

# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

_DEFAULT_RETRIES = 3
_RETRY_DELAY_S = 1.0


class OllamaBackend(LLMBackend):
    """Task extraction backend powered by a local Ollama instance.

    Communicates with Ollama's ``/api/generate`` endpoint using ``httpx``
    (no external Ollama SDK).  Includes:

    - Structured JSON prompt for extraction and classification.
    - Automatic retry with linear back-off on transient HTTP errors.
    - Graceful fallback detection via :attr:`is_available`.
    - JSON schema validation with per-field defaults for malformed output.
    """

    def __init__(self, settings: LLMSettings) -> None:
        """Initialise the backend from application settings.

        Args:
            settings (LLMSettings): LLM configuration block.
        """
        self._host = settings.ollama_host.rstrip("/")
        self._model = settings.ollama_model
        self._retries = _DEFAULT_RETRIES
        self._client = httpx.Client(timeout=60.0)

    # ------------------------------------------------------------------
    # LLMBackend interface
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Ping Ollama's root endpoint to check liveness.

        Returns:
            bool: True if Ollama responds within 2 seconds.
        """
        try:
            resp = self._client.get(self._host, timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def extract_tasks(self, transcript: str) -> list[TaskItem]:
        """Extract tasks from a transcript via the Ollama API.

        Args:
            transcript (str): STT transcript text.

        Returns:
            list[TaskItem]: Extracted tasks, empty list on failure.
        """
        if not transcript.strip():
            return []

        prompt = _EXTRACT_PROMPT.format(transcript=transcript.strip())
        raw = self._generate(prompt)
        if raw is None:
            return []

        return self._parse_tasks(raw, source_transcript=transcript)

    def classify_matrix(self, task: TaskItem) -> MatrixQuadrant:
        """Classify a task into a matrix quadrant via Ollama.

        Falls back to :attr:`~taskify.llm.models.MatrixQuadrant.SCHEDULE`
        if the API call fails or returns an unrecognised quadrant.

        Args:
            task (TaskItem): Task to classify.

        Returns:
            MatrixQuadrant: Assigned quadrant.
        """
        prompt = _CLASSIFY_PROMPT.format(
            title=task.title.strip(),
            notes=task.notes.strip(),
        )
        raw = self._generate(prompt)
        if raw is None:
            return MatrixQuadrant.SCHEDULE

        return self._parse_quadrant(raw)

    # ------------------------------------------------------------------
    # Internal: HTTP
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str | None:
        """Call ``/api/generate`` with retry logic.

        Args:
            prompt (str): Formatted prompt string.

        Returns:
            str, optional: Model response text, or None on total failure.
        """
        url = f"{self._host}/api/generate"
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }

        for attempt in range(1, self._retries + 1):
            try:
                resp = self._client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                response_text: str = data.get("response", "")
                return response_text
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Ollama HTTP %s on attempt %d/%d: %s",
                    exc.response.status_code,
                    attempt,
                    self._retries,
                    exc,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Ollama request error on attempt %d/%d: %s",
                    attempt,
                    self._retries,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected Ollama error: %s", exc)
                break

            if attempt < self._retries:
                time.sleep(_RETRY_DELAY_S * attempt)

        logger.error(
            "Ollama backend failed after %d attempts for model '%s'.",
            self._retries,
            self._model,
        )
        return None

    # ------------------------------------------------------------------
    # Internal: parsing
    # ------------------------------------------------------------------

    def _parse_tasks(
        self, raw: str, source_transcript: str = ""
    ) -> list[TaskItem]:
        """Parse a JSON array string into TaskItem objects.

        Invalid or malformed fields are replaced with safe defaults.

        Args:
            raw (str): Raw JSON string from the model.
            source_transcript (str): Original transcript for traceability.

        Returns:
            list[TaskItem]: Validated task list.
        """
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning("Ollama returned non-JSON extraction response.")
            return []

        if not isinstance(data, list):
            logger.warning(
                "Expected JSON array from extraction, got %s.", type(data)
            )
            return []

        tasks: list[TaskItem] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            if not title:
                continue

            quadrant = MatrixQuadrant.SCHEDULE
            try:
                quadrant = MatrixQuadrant.from_string(
                    str(entry.get("quadrant", "schedule"))
                )
            except ValueError:
                pass

            tasks.append(
                TaskItem(
                    title=title,
                    notes=str(entry.get("notes", "")),
                    due_date=str(entry.get("due_date", "")),
                    quadrant=quadrant,
                    source_transcript=source_transcript,
                    confidence=float(entry.get("confidence", 1.0)),
                    tags=[],
                )
            )

        return tasks

    def _parse_quadrant(self, raw: str) -> MatrixQuadrant:
        """Parse a single-key JSON quadrant response.

        Args:
            raw (str): Raw JSON string from the model.

        Returns:
            MatrixQuadrant: Parsed quadrant; defaults to SCHEDULE on error.
        """
        try:
            data = json.loads(raw.strip())
            return MatrixQuadrant.from_string(str(data.get("quadrant", "")))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not parse quadrant from Ollama: %s", exc)
            return MatrixQuadrant.SCHEDULE

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> OllamaBackend:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
