"""Phase 3 generation defaults (aligned with PhaseWiseArchitecture.md)."""

from __future__ import annotations

import json
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_MANIFEST_PATH = PROJECT_ROOT / "config" / "corpus_manifest.json"


def _load_allowed_citation_urls() -> tuple[str, ...]:
    if CORPUS_MANIFEST_PATH.is_file():
        data = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
        urls = tuple(str(s["url"]) for s in data.get("sources", []) if s.get("url"))
        if urls:
            return urls
    return (
        "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
        "https://groww.in/mutual-funds/bandhan-small-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/quant-small-cap-fund-direct-plan-growth",
        "https://groww.in/mutual-funds/sbi-gold-fund-direct-growth",
    )


def _load_out_of_scope_message() -> str:
    if CORPUS_MANIFEST_PATH.is_file():
        data = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
        schemes: list[str] = []
        for src in data.get("sources", []):
            observed = src.get("scheme_names_observed") or []
            if observed:
                schemes.append(str(observed[0]))
            elif src.get("amc_name"):
                schemes.append(str(src["amc_name"]))
        if schemes:
            if len(schemes) == 1:
                listed = schemes[0]
            else:
                listed = ", ".join(schemes[:-1]) + f", and {schemes[-1]}"
            return (
                "I am a mutual fund FAQ assistant covering only these schemes in my sources: "
                f"{listed}. Your question is outside the scope of my current data."
            )
    return (
        "I am a mutual fund FAQ assistant with a limited indexed corpus. "
        "Your question is outside the scope of my current data."
    )

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

OUT_OF_SCOPE_MESSAGE = _load_out_of_scope_message()

# Paths and API defaults
PHASE2_DIR = Path(os.environ.get("PHASE2_DIR", str(PROJECT_ROOT / "data/phase2_results")))
REFUSAL_TAXONOMY_PATH = PROJECT_ROOT / "phase0" / "refusal_taxonomy.json"

# HTTP API (Phase 3 backend for Phase 4 UI)
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

# Allowed corpus citation URLs (from corpus manifest)
ALLOWED_CITATION_URLS: tuple[str, ...] = _load_allowed_citation_urls()

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
