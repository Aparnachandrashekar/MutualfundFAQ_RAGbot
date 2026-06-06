"""Phase 3 generation defaults (aligned with PhaseWiseArchitecture.md)."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load project-root .env if present (optional dependency)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


_load_dotenv()

# Groq LLM (Phase 3 answer generation)
GROQ_API_KEY_ENV = "GROQ_API_KEY"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE = 0.1
GROQ_MAX_TOKENS = 150

# Retrieval evidence gate
MIN_RETRIEVAL_SCORE = 0.02
MIN_QUERY_TERM_OVERLAP = 0.25
MIN_RRF_SCORE = 0.015
DEFAULT_TOP_K = 5

# Response formatting
MAX_SENTENCES = 3
MAX_CHARS_PER_SENTENCE = 200
NO_ANSWER_MESSAGE = "I don't have information about that in my current data."

OUT_OF_SCOPE_MESSAGE = (
    "I am a mutual fund FAQ assistant covering only five AMCs in my sources: "
    "Choice, Unifi, Union, ICICI Prudential, and LIC Mutual Fund. "
    "Your question is outside the scope of my current data."
)

# Paths and API defaults
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE2_DIR = Path(os.environ.get("PHASE2_DIR", str(PROJECT_ROOT / "data/phase2_results")))
REFUSAL_TAXONOMY_PATH = PROJECT_ROOT / "phase0" / "refusal_taxonomy.json"

# HTTP API (Phase 3 backend for Phase 4 UI)
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

# Allowed corpus citation URLs (Phase 0 allowlist)
ALLOWED_CITATION_URLS: tuple[str, ...] = (
    "https://groww.in/mutual-funds/amc/choice-mutual-funds",
    "https://groww.in/mutual-funds/amc/unifi-mutual-funds",
    "https://groww.in/mutual-funds/amc/union-mutual-funds",
    "https://groww.in/mutual-funds/amc/icici-prudential-mutual-funds",
    "https://groww.in/mutual-funds/amc/lic-mutual-funds",
)

# Educational links for advisory/comparison refusals only (not corpus)
EDUCATIONAL_LINKS: dict[str, str] = {
    "advisory": "https://www.amfiindia.com/investor-corner/knowledge-center",
    "comparison": "https://investor.sebi.gov.in/",
}

STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "what", "how", "does", "do",
    "tell", "me", "about", "of", "for", "in", "on", "to", "and", "or", "my",
    "our", "can", "you", "i", "it", "this", "that", "with", "from", "be",
})
