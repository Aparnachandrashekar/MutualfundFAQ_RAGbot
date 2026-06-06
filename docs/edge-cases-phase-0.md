# Edge cases — Phase 0 (Corpus design and compliance baseline)

Companion to **Phase 0** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: fixed **five** Groww AMC URLs only; refusal taxonomy; no PII.

---

## Scope and allowlist

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Stakeholder asks to add AMC pages, factsheets, or regulator PDFs | Breaks “exactly these URLs” unless you formally revise the constraint | Treat as a **scope change**: update Phase 0 table, re-run ingestion (Phase 1), rebuild index (Phase 2), re-QA citations (Phase 3). |
| A factual answer is **not** present on any of the five pages | Corpus cannot support the question | Document as **known limitation**; assistant should say information is not in the current sources (and refuse speculation). Do not invent URLs. |
| Same scheme name appears in marketing copy with ambiguous category | Wrong user expectations | In Phase 0 manifest, record **scheme names as shown on each page** and note AMC; retrieval filters use this metadata in Phase 2. |

---

## Refusal taxonomy and policy

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Query mixes fact + advice (“What is the expense ratio and should I buy?”) | Partial advisory contaminates compliance | Classify as **advisory** (or split: refuse the advice part; answer the factual part only if policy allows, with strict grounding). |
| “Educational” refusal link points to content that feels like a recommendation | Undermines facts-only positioning | Pre-approve a **short list** of AMFI/SEBI pages; avoid fund picks or “best” lists. |
| Tax / legal question stated as fact but interpretation-heavy | Blurs facts vs guidance | Route to refusal + regulator link, or short factual boundary (“general information only; consult a professional”) per legal review. |

---

## Compliance

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Team wants to log user questions for “analytics” | Risk of storing PII pasted accidentally | **Do not** log free text by default, or scrub patterns (PAN-like, phone digits) per Problemstatement constraints. |
| Internal docs cite Groww as “official” | Misaligned with regulatory wording | In README/limitations, state clearly: corpus is **these five pages** for this project; not a substitute for SID/KIM from AMC. |

---

## Review checklist (Phase 0 exit)

- [ ] Allowlist contains **only** the five URLs; no shadow URLs in configs.
- [ ] Refusal taxonomy covers: single-fund advice, comparison, ranking, “best”, timing/market calls.
- [ ] Educational links for refusals are fixed and reviewed.
