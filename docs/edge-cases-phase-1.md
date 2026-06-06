# Edge cases — Phase 1 (Ingestion and curated knowledge base)

Companion to **Phase 1** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: fetch **only** the five allowlisted URLs; HTML → text; auditable storage.

---

## Fetching and availability

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| HTTP 403 / bot blocking / CAPTCHA | Empty or partial corpus | Retry with backoff; respectful `User-Agent`; if persistent, **fail the job visibly** and surface “sources unavailable” in ops—not silent empty index. |
| HTTP 429 rate limiting | Incomplete ingestion | Throttle client; schedule staggered fetches per URL; record partial status per URL. |
| Timeout / TLS / DNS failures | Missing AMC slice | Per-URL success flags; do not mark pipeline green until all **five** succeed or policy accepts degraded mode with explicit UI warning. |
| Page returns 200 but with “access denied” body | Looks ingested but content is junk | Validate minimum text length and expected markers (e.g., fund table keywords); quarantine bad snapshots. |

---

## Parsing and normalization

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Heavy JS-rendered content; fetcher sees shell HTML | Near-empty text | Use a strategy that matches reality (e.g., headless browser **only if** project allows); otherwise document **cannot ingest** dynamic-only bits. |
| Duplicate boilerplate (header/footer) on every page | Dominates chunks; hurts retrieval | Strip nav, cookie banners, footers; keep **one** canonical `source_url` per stored doc. |
| Table extraction breaks (merged cells, “See more”) | Wrong exit load / min SIP | Prefer structured extraction rules for tables; QA samples per AMC page after changes. |
| Encoding / odd whitespace / `\u00a0` | Broken tokenization | Normalize Unicode and whitespace before chunking. |

---

## Versioning and audit

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Source page updates between ingest and user query | “Last updated” feels wrong | Store **`ingested_at` per fetch**; footer uses defined policy (e.g., max date among chunks used—Phase 3). |
| Need to prove what text was in corpus at time T | Compliance / debugging | Keep immutable raw HTML snapshots or checksums per ingest run. |

---

## Review checklist (Phase 1 exit)

- [ ] All **five** URLs have successful latest extracts or explicit degraded-state handling.
- [ ] No crawl beyond hostname/path of allowlisted URLs.
- [ ] Raw + cleaned text and timestamps are stored for reproducibility.
