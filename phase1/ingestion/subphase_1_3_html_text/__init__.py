"""Phase 1.3 — HTML → normalized text."""

from phase1.ingestion.subphase_1_3_html_text.extract import (
    DEFAULT_MIN_CLEAN_TEXT_CHARS,
    check_min_length,
    decode_html_bytes,
    html_bytes_to_normalized_text,
    normalize_whitespace,
)

__all__ = [
    "DEFAULT_MIN_CLEAN_TEXT_CHARS",
    "check_min_length",
    "decode_html_bytes",
    "html_bytes_to_normalized_text",
    "normalize_whitespace",
]
