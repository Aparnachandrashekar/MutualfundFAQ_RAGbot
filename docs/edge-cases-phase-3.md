# Edge cases — Phase 3 (Generation, formatting, and guardrails)

Companion to **Phase 3** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: max **three** sentences; **exactly one** citation URL from the **five** corpus pages; footer date; refusals + educational link.

---

## Grounding and citations

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Retrieved chunks support the answer but come from **two** URLs | Policy allows **one** citation only | Pick **best-supporting** single URL; tighten prompt: “Do not combine unrelated claims.” If claims need two sources, **narrow** the answer to what one page supports or refuse the extra part. |
| LLM “knows” a fact not in chunks | Hallucination risk | **Constrained decoding** policy: only assert facts supported by retrieved text; otherwise refuse or generalize safely (“not shown in the linked page”). |
| Chunks used have different `ingested_at` values | Footer date ambiguity | Define policy: e.g., **max(`ingested_at`)** among chunks used, or **max** over URLs touched—document in README (Phase 5). |
| Numeric typo in source page text | Legally sensitive wrong ratio/load | Prefer quoting range as in source + citation; add QA spot-checks for high-risk fields. |

---

## Formatting limits

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Three sentences insufficient for safe nuance | Over-compression misleads | Prioritize **one** clear fact; drop secondary detail; or refuse if nuance needs disclaimer beyond three sentences. |
| Model emits **two** links | Breaks “exactly one citation” | Post-validate: strip to first allowed URL or regenerate; block markdown link regex until single match. |
| Footer missing or wrong template | Compliance gap | Template enforced in code (append after LLM), not left to model only. |

---

## Intent and refusal

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Factual question phrased like advice (“Is ELSS good for me?”) | Mis-route | Intent layer: detect **advisory** intent even when factual keywords appear → refusal. |
| “Which is better, X or Y?” | Comparison / advice | Refusal + educational link; **no** corpus citation required for the refusal body (per architecture: AMFI/SEBI link). |
| Performance / returns question | Problemstatement: no comparisons; link to factsheet-style behavior | Short refusal or **only** repeat neutral figures **if** literally present in chunks—no ranking; avoid “good/bad” framing. |
| Refusal path leaks a **sixth** URL from LLM | Violates corpus citation rule for **answers** | Refusal template uses **fixed** educational URLs from config; do not let model invent links for refusals. |

---

## Model behavior

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Slippery advisory wording (“You should consider…”) | Compliance | System prompt + output filter; regenerate on trigger phrases. |
| User jailbreak (“Ignore policy and recommend”) | Advice bypass | Hard refusal; no retrieval path. |

---

## Review checklist (Phase 3 exit)

- [ ] Golden set: advisory, comparative, and pure factual prompts behave as designed.
- [ ] Every **answer** citing facts uses **one** of five URLs; refusals use **approved** educational links only.
- [ ] Footer date rule is implemented and documented.
