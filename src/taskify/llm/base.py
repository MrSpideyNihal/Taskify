"""Abstract base class for LLM/NLP task extraction backends."""

from abc import ABC, abstractmethod

from taskify.llm.models import MatrixQuadrant, TaskItem


class LLMBackend(ABC):
    """Interface all task-extraction backends must implement."""

    @abstractmethod
    def extract_tasks(self, transcript: str) -> list[TaskItem]:
        """Extract actionable tasks from a speech transcript.

        Args:
            transcript (str): Raw transcript text from the STT engine.

        Returns:
            list[TaskItem]: Zero or more extracted task items.
        """

    @abstractmethod
    def classify_matrix(self, task: TaskItem) -> MatrixQuadrant:
        """Classify a task into an Eisenhower Matrix quadrant.

        Args:
            task (TaskItem): Task to classify.

        Returns:
            MatrixQuadrant: The assigned quadrant.
        """

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backend can currently accept requests.

        Used by the factory to fall back to the NLP backend when Ollama
        is not running.

        Returns:
            bool: Availability flag.
        """
