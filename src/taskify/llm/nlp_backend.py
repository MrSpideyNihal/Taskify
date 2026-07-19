"""Rule-based NLP backend for task extraction without an LLM.

Works with **zero optional dependencies** using pure regex/keyword heuristics.
When ``spaCy`` (with ``en_core_web_sm`` or equivalent) is installed it
automatically activates an improved recall path that uses:

- Named Entity Recognition (NER) for date/deadline extraction.
- Dependency-parse based imperative verb detection.

The two code paths are exercised by the unit tests so CI never requires spaCy.
"""

from __future__ import annotations

import re
from typing import Any

from taskify.llm.base import LLMBackend
from taskify.llm.models import MatrixQuadrant, TaskItem

# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

# Signals that push a task toward "Urgent"
_URGENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "urgent",
        "urgently",
        "asap",
        "immediately",
        "right now",
        "today",
        "tonight",
        "this morning",
        "this afternoon",
        "critical",
        "emergency",
        "deadline",
        "due today",
        "by end of day",
        "eod",
        "now",
        "quickly",
        "straight away",
        "at once",
        "before noon",
        "before tonight",
        "before end of day",
    }
)

# Signals that push a task toward "Important"
_IMPORTANT_KEYWORDS: frozenset[str] = frozenset(
    {
        "important",
        "crucial",
        "essential",
        "must",
        "need to",
        "have to",
        "priority",
        "key",
        "critical",
        "significant",
        "vital",
        "necessary",
        "strategic",
        "milestone",
        "goal",
        "objective",
        "project",
    }
)

# Signals that suppress importance ("not important")
_LOW_IMPORTANCE_KEYWORDS: frozenset[str] = frozenset(
    {
        "someday",
        "maybe",
        "eventually",
        "whenever",
        "nice to have",
        "low priority",
        "not important",
        "minor",
        "trivial",
        "later",
        "at some point",
        "if possible",
        "could",
        "might",
    }
)

# Delegation signals
_DELEGATE_KEYWORDS: frozenset[str] = frozenset(
    {
        "ask",
        "remind",
        "tell",
        "have someone",
        "delegate",
        "assign",
        "request",
        "get someone",
        "let someone",
        "make sure someone",
        "have them",
        "have him",
        "have her",
    }
)

# Common imperative verbs to seed extraction
_IMPERATIVE_VERBS: frozenset[str] = frozenset(
    {
        "buy",
        "call",
        "check",
        "clean",
        "complete",
        "confirm",
        "contact",
        "create",
        "do",
        "draft",
        "email",
        "file",
        "find",
        "finish",
        "fix",
        "follow",
        "get",
        "go",
        "handle",
        "install",
        "make",
        "meet",
        "order",
        "pay",
        "pick",
        "plan",
        "prepare",
        "print",
        "purchase",
        "read",
        "register",
        "remind",
        "reply",
        "research",
        "review",
        "schedule",
        "send",
        "set",
        "share",
        "sign",
        "start",
        "submit",
        "talk",
        "update",
        "upload",
        "write",
        "book",
        "cancel",
        "change",
        "close",
        "collect",
        "connect",
        "delete",
        "design",
        "download",
        "drop",
        "edit",
        "enter",
        "fill",
        "give",
        "help",
        "join",
        "launch",
        "move",
        "notify",
        "open",
        "provide",
        "push",
        "record",
        "remove",
        "report",
        "request",
        "return",
        "run",
        "save",
        "ship",
        "show",
        "sort",
        "speak",
        "take",
        "test",
        "track",
        "transfer",
        "visit",
    }
)

# Relative date phrases that imply a deadline
_DATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(today|tonight|tomorrow|this (morning|afternoon|evening|week|weekend"
        r"|month|year))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(next\s+(week|month|year|monday|tuesday|wednesday|thursday|friday"
        r"|saturday|sunday))\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b"),  # Full ISO: 2025-08-01
    re.compile(
        r"\b(\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(january|february|march|april|may|june|july|august|september"
        r"|october|november|december)\s+\d{1,2}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bby\s+(end\s+of\s+(day|week|month)|eod|eow|eom)\b", re.IGNORECASE),
    re.compile(r"\bin\s+\d+\s+(days?|weeks?|months?)\b", re.IGNORECASE),
]

# Sentence / clause boundary splitter
_SPLIT_PATTERN = re.compile(r"[.!?;,\n]+")

# Imperative sentence starter pattern
_IMPERATIVE_PATTERN = re.compile(
    r"^\s*(?:please\s+|I need (?:to\s+|you to\s+)?|"
    r"(?:I\s+(?:have|need)\s+to\s+)|(?:we\s+(?:need|have)\s+to\s+)|"
    r"(?:can you\s+)|(?:could you\s+)|(?:make sure\s+(?:to\s+)?)|"
    r"(?:don\'t forget\s+(?:to\s+)?))?("
    + "|".join(re.escape(v) for v in sorted(_IMPERATIVE_VERBS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _contains_any(text: str, keywords: frozenset[str]) -> bool:
    """Return True if *text* contains any keyword (word-boundary aware)."""
    lower = text.lower()
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", lower):
            return True
    return False


def _extract_date(text: str) -> str:
    """Return the first date-like phrase found in *text*, or empty string."""
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return ""


def _classify_quadrant_heuristic(sentence: str) -> MatrixQuadrant:
    """Classify a sentence into a quadrant using keyword heuristics.

    Args:
        sentence (str): Source sentence (or full transcript).

    Returns:
        MatrixQuadrant: Best-fit quadrant.
    """
    is_urgent = _contains_any(sentence, _URGENT_KEYWORDS)
    is_important = _contains_any(sentence, _IMPORTANT_KEYWORDS)
    is_low = _contains_any(sentence, _LOW_IMPORTANCE_KEYWORDS)
    is_delegate = _contains_any(sentence, _DELEGATE_KEYWORDS)

    if is_delegate and is_urgent:
        return MatrixQuadrant.DELEGATE
    if is_delegate and not is_important:
        return MatrixQuadrant.DELEGATE
    if is_low and not is_urgent:
        return MatrixQuadrant.ELIMINATE
    if is_urgent and is_important:
        return MatrixQuadrant.DO_FIRST
    if is_urgent:
        return MatrixQuadrant.DO_FIRST
    if is_important:
        return MatrixQuadrant.SCHEDULE
    if is_low:
        return MatrixQuadrant.ELIMINATE
    return MatrixQuadrant.SCHEDULE


def _title_case_sentence(text: str) -> str:
    """Capitalise the first letter, preserving the rest."""
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


# ---------------------------------------------------------------------------
# Rule-based extraction (no spaCy)
# ---------------------------------------------------------------------------


def _extract_tasks_regex(transcript: str) -> list[TaskItem]:
    """Extract tasks using pure regex/keyword rules.

    Splits transcript on sentence boundaries, then looks for clauses that
    begin with an imperative verb or contain action signals.

    Args:
        transcript (str): Raw transcript text.

    Returns:
        list[TaskItem]: Extracted task candidates.
    """
    clauses = [c.strip() for c in _SPLIT_PATTERN.split(transcript) if c.strip()]
    tasks: list[TaskItem] = []
    seen_titles: set[str] = set()

    for clause in clauses:
        if len(clause.split()) < 2:
            continue  # Skip single-word fragments

        # Match imperative verb at start (with optional softeners)
        m = _IMPERATIVE_PATTERN.match(clause)
        if not m:
            # Fall back: "I need to X", "don't forget to X" etc.
            if not re.search(
                r"\b(need to|have to|must|should|don.t forget|make sure)\b",
                clause,
                re.IGNORECASE,
            ):
                continue

        title = _title_case_sentence(clause)
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        due_date = _extract_date(clause)
        quadrant = _classify_quadrant_heuristic(clause)

        tasks.append(
            TaskItem(
                title=title,
                notes="",
                due_date=due_date,
                quadrant=quadrant,
                source_transcript=transcript,
                confidence=0.7,
            )
        )

    return tasks


# ---------------------------------------------------------------------------
# spaCy-enhanced extraction (optional)
# ---------------------------------------------------------------------------


def _try_load_spacy() -> Any:
    """Attempt to import and load the spaCy English model.

    Returns:
        spaCy Language model or None if not installed / model missing.
    """
    try:
        import spacy  # noqa: PLC0415

        return spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        return None


def _extract_tasks_spacy(transcript: str, nlp: Any) -> list[TaskItem]:
    """Extract tasks using spaCy dependency parsing and NER.

    Uses:
    - Dependency parse to find ROOT verbs (imperatives) in each sentence.
    - Named entities of type DATE/TIME for deadline extraction.
    - Keyword heuristics for quadrant classification.

    Args:
        transcript (str): Raw transcript text.
        nlp: spaCy Language model.

    Returns:
        list[TaskItem]: Extracted task items.
    """
    doc = nlp(transcript)
    tasks: list[TaskItem] = []
    seen_titles: set[str] = set()

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if len(sent_text.split()) < 2:
            continue

        # Find ROOT verb — candidate imperative
        root_token = None
        for token in sent:
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                root_token = token
                break

        # Accept sentence if root verb is an imperative verb, OR rule matches
        is_imperative = (
            root_token is not None and root_token.lemma_.lower() in _IMPERATIVE_VERBS
        ) or bool(_IMPERATIVE_PATTERN.match(sent_text))

        if not is_imperative and not re.search(
            r"\b(need to|have to|must|should|don.t forget|make sure)\b",
            sent_text,
            re.IGNORECASE,
        ):
            continue

        title = _title_case_sentence(sent_text)
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Extract DATE/TIME entities for due_date
        due_date = ""
        for ent in sent.ents:
            if ent.label_ in ("DATE", "TIME"):
                due_date = ent.text.strip()
                break
        if not due_date:
            due_date = _extract_date(sent_text)

        quadrant = _classify_quadrant_heuristic(sent_text)

        tasks.append(
            TaskItem(
                title=title,
                notes="",
                due_date=due_date,
                quadrant=quadrant,
                source_transcript=transcript,
                confidence=0.85,
            )
        )

    return tasks


# ---------------------------------------------------------------------------
# NLPBackend
# ---------------------------------------------------------------------------


class NLPBackend(LLMBackend):
    """Rule-based task extraction backend with optional spaCy enhancement.

    Requires no external services. Works offline and always returns results
    even if Ollama is unavailable.

    If the ``spaCy`` library and ``en_core_web_sm`` model are installed the
    backend automatically uses the higher-recall NLP path; otherwise it
    falls back to pure regex heuristics.
    """

    def __init__(self) -> None:
        """Initialise the backend, loading spaCy if available."""
        self._nlp: Any = _try_load_spacy()
        self._using_spacy: bool = self._nlp is not None

    @property
    def is_available(self) -> bool:
        """NLP backend is always available (no external service needed).

        Returns:
            bool: Always True.
        """
        return True

    @property
    def using_spacy(self) -> bool:
        """Return True when the spaCy model was successfully loaded.

        Returns:
            bool: spaCy availability.
        """
        return self._using_spacy

    def extract_tasks(self, transcript: str) -> list[TaskItem]:
        """Extract tasks from a transcript using NLP/regex heuristics.

        Args:
            transcript (str): Raw transcript text.

        Returns:
            list[TaskItem]: Extracted task items.
        """
        if not transcript.strip():
            return []

        if self._using_spacy:
            return _extract_tasks_spacy(transcript, self._nlp)
        return _extract_tasks_regex(transcript)

    def classify_matrix(self, task: TaskItem) -> MatrixQuadrant:
        """Classify a single task using keyword heuristics.

        Args:
            task (TaskItem): Task to classify.

        Returns:
            MatrixQuadrant: Assigned quadrant.
        """
        combined = f"{task.title} {task.notes}"
        return _classify_quadrant_heuristic(combined)
