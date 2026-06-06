# Compliance checklist (Phase 0)

Aligned with [Problemstatement.md](../Problemstatement.md) and [PhaseWiseArchitecture.md](../PhaseWiseArchitecture.md).

## Data and sources

- [ ] Corpus ingestion restricted to URLs in [`config/corpus_manifest.json`](../config/corpus_manifest.json) (five Groww AMC pages only).
- [ ] No third-party blogs or aggregators added to the corpus without a formal allowlist change.
- [ ] Team understands Groww pages are the **entire** RAG corpus for this project—not AMC SID/KIM PDFs unless scope changes.

## Privacy and security

- [ ] No collection, storage, or processing of PAN, Aadhaar, account numbers, OTPs, email, or phone numbers in the assistant design.
- [ ] Analytics/logging plans reviewed so raw chat does not retain PII (see [edge cases Phase 4](../docs/edge-cases-phase-4.md)).

## Content restrictions

- [ ] Facts-only posture documented; refusal taxonomy signed off ([`refusal_taxonomy.json`](./refusal_taxonomy.json)).
- [ ] No investment advice, ratings as recommendations, or performance comparisons in approved answer templates.
- [ ] Educational links for refusals taken from [`refusal_taxonomy.json`](./refusal_taxonomy.json) allowlist (or updated via review).

## Transparency

- [ ] Planned answer shape: max three sentences, exactly one citation URL from the five corpus URLs, plus “Last updated from sources” footer (implemented in Phase 3).

## Sign-off

| Item | Owner | Date |
|------|-------|------|
| Corpus allowlist (5 URLs) | | |
| Refusal taxonomy | | |
| This checklist | | |
