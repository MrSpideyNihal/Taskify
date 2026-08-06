"""Unit tests for NLPBackend — rule-based and spaCy-enhanced extraction paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from taskify.llm.models import MatrixQuadrant, TaskItem
from taskify.llm.nlp_backend import (
    NLPBackend,
    _classify_quadrant_heuristic,
    _extract_date,
    _extract_tasks_regex,
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


class TestExtractDate:
    def test_today(self) -> None:
        assert _extract_date("I need to call Tom today") == "today"

    def test_tomorrow(self) -> None:
        assert _extract_date("Ship the report tomorrow morning") == "tomorrow"

    def test_weekday(self) -> None:
        result = _extract_date("Meeting on Friday")
        assert "friday" in result.lower()

    def test_next_week(self) -> None:
        result = _extract_date("Submit the proposal next week")
        assert "next" in result.lower()

    def test_iso_date(self) -> None:
        assert "2025-08-01" in _extract_date("Deadline is 2025-08-01")

    def test_no_date(self) -> None:
        assert _extract_date("Buy milk") == ""


class TestClassifyQuadrantHeuristic:
    def test_urgent_important_gives_do_first(self) -> None:
        assert (
            _classify_quadrant_heuristic("Fix critical bug before end of day urgently")
            == MatrixQuadrant.DO_FIRST
        )

    def test_important_not_urgent_gives_schedule(self) -> None:
        assert (
            _classify_quadrant_heuristic("Plan the new project goals")
            == MatrixQuadrant.SCHEDULE
        )

    def test_low_importance_gives_eliminate(self) -> None:
        assert (
            _classify_quadrant_heuristic("Someday I might reorganise the bookshelf")
            == MatrixQuadrant.ELIMINATE
        )

    def test_delegate_urgent_gives_delegate(self) -> None:
        assert (
            _classify_quadrant_heuristic("Ask John to send the file urgently")
            == MatrixQuadrant.DELEGATE
        )

    def test_delegate_not_important_gives_delegate(self) -> None:
        assert (
            _classify_quadrant_heuristic("Remind Sarah about the meeting")
            == MatrixQuadrant.DELEGATE
        )

    def test_default_is_schedule(self) -> None:
        # No keywords → default
        assert _classify_quadrant_heuristic("Buy oat milk") == MatrixQuadrant.SCHEDULE


# ---------------------------------------------------------------------------
# Rule-based extraction (no spaCy)
# ---------------------------------------------------------------------------


class TestExtractTasksRegex:
    def test_simple_imperative(self) -> None:
        tasks = _extract_tasks_regex("Buy groceries on the way home.")
        assert len(tasks) >= 1
        assert any("buy" in t.title.lower() for t in tasks)

    def test_need_to_phrase(self) -> None:
        tasks = _extract_tasks_regex("I need to submit the report by Friday.")
        assert len(tasks) >= 1

    def test_have_to_phrase(self) -> None:
        tasks = _extract_tasks_regex("I have to call the doctor today.")
        assert len(tasks) >= 1
        assert tasks[0].due_date != ""

    def test_multiple_imperatives(self) -> None:
        transcript = "Call the dentist. Send the invoice. Buy birthday cake."
        tasks = _extract_tasks_regex(transcript)
        assert len(tasks) == 3

    def test_deduplication(self) -> None:
        tasks = _extract_tasks_regex("Buy milk. Buy milk. Buy milk.")
        assert len(tasks) == 1

    def test_empty_transcript_returns_empty(self) -> None:
        assert _extract_tasks_regex("") == []
        assert _extract_tasks_regex("   ") == []

    def test_single_word_fragments_ignored(self) -> None:
        tasks = _extract_tasks_regex("Okay. Yes. Sure. Maybe.")
        assert tasks == []

    def test_quadrant_assigned_on_urgency(self) -> None:
        tasks = _extract_tasks_regex("Fix the critical bug immediately.")
        assert len(tasks) >= 1
        assert tasks[0].quadrant == MatrixQuadrant.DO_FIRST

    def test_deadline_extracted(self) -> None:
        tasks = _extract_tasks_regex("Submit proposal by next week.")
        due_dates = [t.due_date for t in tasks]
        assert any(d != "" for d in due_dates)

    def test_confidence_is_set(self) -> None:
        tasks = _extract_tasks_regex("Buy milk today.")
        assert all(0.0 <= t.confidence <= 1.0 for t in tasks)

    def test_source_transcript_attached(self) -> None:
        transcript = "Call the bank today."
        tasks = _extract_tasks_regex(transcript)
        assert all(t.source_transcript == transcript for t in tasks)

    def test_please_prefix_stripped(self) -> None:
        tasks = _extract_tasks_regex("Please send the document today.")
        assert len(tasks) >= 1
        assert "please" not in tasks[0].title.lower()

    def test_punctuation_less_segmentation(self) -> None:
        transcript = (
            "make a python script to detect square so i need to "
            "pick up my lunch tiffin as quick as possible"
        )
        tasks = _extract_tasks_regex(transcript)
        assert len(tasks) == 2
        # Title 1
        assert "make" in tasks[0].title.lower()
        # Title 2
        assert "pick" in tasks[1].title.lower()
        # Quadrant 2 should be DO_FIRST due to "quick"
        assert tasks[1].quadrant == MatrixQuadrant.DO_FIRST

    def test_title_cleaning_and_notes(self) -> None:
        transcript = (
            "so i need to call the client and explain the new "
            "project design details as soon as possible"
        )
        tasks = _extract_tasks_regex(transcript)
        assert len(tasks) == 1
        # Title should be truncated/cleaned (no more than 10 words or full phrase)
        assert len(tasks[0].title.split()) <= 11
        # Key action phrase should appear in either the title or notes
        assert "explain the new project design" in (
            tasks[0].title + " " + tasks[0].notes
        ).lower()

    def test_title_auto_summarization_strips_priority(self) -> None:
        transcript = "send an important and urgent image as soon as possible"
        tasks = _extract_tasks_regex(transcript)
        assert len(tasks) == 1
        assert tasks[0].title == "Send an image"



# ---------------------------------------------------------------------------
# NLPBackend public interface
# ---------------------------------------------------------------------------


class TestNLPBackend:
    def test_always_available(self) -> None:
        backend = NLPBackend()
        assert backend.is_available is True

    def test_extract_tasks_returns_list(self) -> None:
        backend = NLPBackend()
        result = backend.extract_tasks("Buy oat milk and call the dentist.")
        assert isinstance(result, list)

    def test_empty_transcript_returns_empty(self) -> None:
        backend = NLPBackend()
        assert backend.extract_tasks("") == []
        assert backend.extract_tasks("   ") == []

    def test_classify_matrix_returns_quadrant(self) -> None:
        backend = NLPBackend()
        task = TaskItem(title="Fix critical server crash", notes="urgent")
        result = backend.classify_matrix(task)
        assert isinstance(result, MatrixQuadrant)
        assert result == MatrixQuadrant.DO_FIRST

    def test_classify_matrix_schedule_default(self) -> None:
        backend = NLPBackend()
        task = TaskItem(title="Write documentation")
        result = backend.classify_matrix(task)
        assert result == MatrixQuadrant.SCHEDULE

    def test_classify_matrix_eliminate(self) -> None:
        backend = NLPBackend()
        task = TaskItem(title="Reorganise old files someday", notes="low priority")
        result = backend.classify_matrix(task)
        assert result == MatrixQuadrant.ELIMINATE

    def test_uses_spacy_when_loaded(self) -> None:
        """When spaCy load succeeds, using_spacy should be True."""
        mock_nlp = MagicMock()
        mock_nlp.return_value = MagicMock()

        with patch("taskify.llm.nlp_backend._try_load_spacy", return_value=mock_nlp):
            backend = NLPBackend()
            assert backend.using_spacy is True

    def test_falls_back_to_regex_when_spacy_missing(self) -> None:
        """When spaCy is not installed, using_spacy should be False."""
        with patch("taskify.llm.nlp_backend._try_load_spacy", return_value=None):
            backend = NLPBackend()
            assert backend.using_spacy is False

    def test_spacy_path_calls_extract_spacy(self) -> None:
        """extract_tasks uses the spaCy path when _nlp is set."""
        mock_nlp = MagicMock()
        # spaCy doc mock: two sentences each with one imperative token
        fake_sent_1 = MagicMock()
        fake_sent_1.text = "Call the dentist today."
        fake_sent_1.ents = []
        fake_sent_2 = MagicMock()
        fake_sent_2.text = "Send the invoice."
        fake_sent_2.ents = []

        for sent in [fake_sent_1, fake_sent_2]:
            root = MagicMock()
            root.dep_ = "ROOT"
            root.pos_ = "VERB"
            root.lemma_ = "call"
            sent.__iter__ = MagicMock(return_value=iter([root]))

        fake_doc = MagicMock()
        fake_doc.sents = [fake_sent_1, fake_sent_2]
        mock_nlp.return_value = fake_doc

        with patch("taskify.llm.nlp_backend._try_load_spacy", return_value=mock_nlp):
            backend = NLPBackend()

        mock_nlp.return_value = fake_doc
        backend._nlp = mock_nlp

        result = backend.extract_tasks("Call the dentist today. Send the invoice.")
        assert isinstance(result, list)
