# Edge cases — Phase 5 (Packaging, documentation, and operational clarity)

Companion to **Phase 5** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: README, env examples, reindex instructions, known limitations, disclaimer snippet.

---

## Documentation accuracy

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| README lists wrong corpus URLs or omits one of five | Users debug wrong allowlist | **Copy-paste** URLs from Phase 0 table; automated check in CI that manifest matches README list. |
| “Architecture overview” drifts from actual code | Onboarding confusion | Link README to `PhaseWiseArchitecture.md`; single source of truth for phases. |
| Known limitations section empty | Hidden expectations | Explicitly state: **five Groww AMC pages only**; stale data risk; no AMC PDFs. |

---

## Secrets and configuration

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| `.env.example` contains placeholder that looks real | Accidental commit of keys | Use obvious placeholders (`YOUR_KEY_HERE`); never real tokens. |
| Docs tell users to `export ANTHROPIC_API_KEY=sk-...` in shell history | Leak risk | Prefer secret manager or local `.env` gitignored; document **never commit `.env`**. |
| Multiple embedding providers documented | Reader picks wrong combo | One **default** path; others “advanced”. |

---

## Operations and reproducibility

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| New developer runs app **without** building index | Empty retrieval / errors | README **quickstart** order: deps → ingest → build index → run API → run UI. |
| Ingestion uses live network; CI cannot run E2E | Flaky CI | Mock fixtures for tests; optional nightly job against live five URLs with alerts. |
| Source pages change; answers shift | User trust | Document **re-ingest schedule**; changelog note when corpus refresh happens. |

---

## Handoff and versioning

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Python/Node version unspecified | “Works on my machine” | Pin versions in `pyproject` / `package.json` / `.tool-versions`. |
| Model name in README does not match deployed model | Evaluation mismatch | Version table: embedding model, LLM, chunk params, index build date. |

---

## Review checklist (Phase 5 exit)

- [ ] All **five** corpus URLs listed and correct.
- [ ] Limitations and non-goals are explicit (narrow corpus, third-party page dependency).
- [ ] One command sequence reproduces a working local demo end-to-end.
