# Edge cases — Phase 2 (Chunking, indexing, and retrieval)

Companion to **Phase 2** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: chunks embed **only** text from the five pages; metadata for citation mapping.

---

## Chunking

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Chunk boundary splits a table row | Nonsense retrieval (“expense” without ratio) | Prefer **table-aware** chunking or smaller overlap; merge rows into single chunk where needed. |
| Two schemes’ facts in one paragraph | Model cites wrong scheme | Tag chunks with **`scheme_id` / scheme name** when extractable; filter at retrieval if user names a fund. |
| Very short chunks (one number only) | Embedding noise; wrong matches | Merge micro-chunks with preceding context up to a max size. |
| Duplicate chunks across pages | Same embedding repeated | Dedupe or down-weight; keep distinct `source_url` per chunk (only five possible URLs). |

---

## Retrieval

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| **Zero** chunks above similarity threshold | Empty context | Return controlled “not found in sources” path; do not fill from LLM general knowledge for factual claims. |
| User asks about **Union** but similarity pulls **Unifi** | Wrong AMC (name collision) | Metadata filter by AMC or keyword gate; optional **disambiguation** prompt (“Did you mean …?”). |
| Top-k all from one AMC when question is broad | Misses relevant fund on another page | Increase `k` modestly; **MMR** or diversity across `source_url`; still cite **one** URL in Phase 3. |
| Query in Hindi / Hinglish; corpus English | Poor retrieval | Transliterate/map key entities (scheme names) in query preprocessing, or document **English-only** scope. |

---

## Embeddings and index

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Embedding model change without full reindex | Silent quality drift | Pin model version; **rebuild index** when model changes; note in Phase 5 docs. |
| API rate limits / embedding failures mid-batch | Partial index | Abort or mark index invalid; never serve half-built index in prod without flag. |

---

## Review checklist (Phase 2 exit)

- [ ] Every chunk carries `source_url` ∈ {five allowlisted URLs}.
- [ ] Golden questions cover each AMC page at least once.
- [ ] Ambiguous fund names have a tested retrieval behavior.
