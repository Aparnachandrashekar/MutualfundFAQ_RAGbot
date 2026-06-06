# Phase 1.3 — HTML → text extraction and normalization

See [PhaseWiseArchitecture.md](../../../PhaseWiseArchitecture.md) §1.3.

**Implemented** in [`extract.py`](./extract.py):

- Decode bytes using `charset=` from `Content-Type` when present, else UTF-8 / Latin-1 fallbacks.
- BeautifulSoup (`html.parser`) removes `script` / `style` / `nav` / `footer` / `header` and rough cookie/consent blocks.
- Unicode **NFKC** + line-level whitespace normalization for stable downstream chunking.
- Default minimum clean-text length **`DEFAULT_MIN_CLEAN_TEXT_CHARS`** (2048); the pipeline fails the run if any source is shorter (catches empty/error shells).

Output file per source: **`clean.txt`** next to `raw.html` when using [`ingest_through_1_3.py`](../ingest_through_1_3.py).
