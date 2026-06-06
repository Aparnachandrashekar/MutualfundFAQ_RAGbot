"""Phase 1.3 — HTML to normalized plain text for chunking."""

from __future__ import annotations

import re
import unicodedata
from re import Pattern

from bs4 import BeautifulSoup


# Groww AMC pages are large; failures usually yield tiny blobs.
DEFAULT_MIN_CLEAN_TEXT_CHARS = 2_048

_WS_LINE: Pattern[str] = re.compile(r"[ \t\f\v]+")


def sniff_charset(content_type_header: str | None) -> str | None:
    if not content_type_header:
        return None
    m = re.search(r"charset=([\w\-]+)", content_type_header, flags=re.I)
    if not m:
        return None
    return m.group(1).strip().strip('"')


def decode_html_bytes(data: bytes, content_type_header: str | None = None) -> str:
    """Decode HTML bytes; tries header charset then common fallbacks."""
    tried: list[str] = []
    cs = sniff_charset(content_type_header)
    for enc in (cs, "utf-8", "utf-8-sig", "latin-1"):
        if not enc or enc in tried:
            continue
        tried.append(enc)
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def normalize_whitespace(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    lines = [_WS_LINE.sub(" ", line).strip() for line in t.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def html_bytes_to_normalized_text(
    html_bytes: bytes,
    *,
    content_type_header: str | None = None,
) -> str:
    """
    Parse HTML, drop structural/nav noise, emit normalized plain text.

    Uses stdlib-compatible ``html.parser`` backend via BeautifulSoup.
    """
    html = decode_html_bytes(html_bytes, content_type_header)
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "template", "iframe"]):
        tag.decompose()

    for tag in soup.find_all(["nav", "footer", "header"]):
        tag.decompose()

    # Best-effort removal of cookie/consent shells (class names vary by site).
    for node in soup.select(
        '[class*="cookie"], [id*="cookie"], '
        '[class*="consent"], [id*="consent"]'
    ):
        node.decompose()

    text = soup.get_text(separator="\n")
    return normalize_whitespace(text)


def check_min_length(text: str, *, minimum: int = DEFAULT_MIN_CLEAN_TEXT_CHARS) -> bool:
    return len(text) >= minimum
