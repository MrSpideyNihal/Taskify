"""Factory for resolving the configured LLM/NLP backend."""

import logging

from taskify.config import Settings
from taskify.llm.base import LLMBackend
from taskify.llm.ollama_backend import OllamaBackend

logger = logging.getLogger(__name__)


def get_llm_backend(settings: Settings) -> LLMBackend:
    """Instantiate and return the configured LLM backend.

    If the primary backend is ``"ollama"`` but the Ollama service is
    unreachable, logs a warning and falls back to the NLP backend
    (implemented in Issue #9).

    Args:
        settings (Settings): Application configuration.

    Returns:
        LLMBackend: Configured backend instance.

    Raises:
        ValueError: If the configured backend name is not recognised.
    """
    backend_name = settings.llm.backend.lower()

    if backend_name == "ollama":
        backend = OllamaBackend(settings.llm)
        if not backend.is_available:
            logger.warning(
                "Ollama is not reachable at '%s'. "
                "Falling back to NLP backend.",
                settings.llm.ollama_host,
            )
            # NLP backend will be imported here once Issue #9 is implemented.
            # For now, return the (unavailable) Ollama instance so callers
            # can detect the outage via is_available and handle accordingly.
        return backend

    if backend_name == "nlp":
        # NLP/spaCy backend: implemented in Issue #9.
        raise NotImplementedError(
            "NLP backend is not yet implemented. Set llm.backend = 'ollama'."
        )

    raise ValueError(
        f"Unknown LLM backend '{settings.llm.backend}'. "
        "Valid choices: 'ollama', 'nlp'."
    )
