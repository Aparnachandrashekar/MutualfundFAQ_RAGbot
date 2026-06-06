# Query scope: factual vs out-of-scope

Rules for classifying user queries. **In-scope** queries are answered from retrieved text on the five allowlisted pages only. **Out-of-scope** queries get a refusal (and educational link) per [`refusal_taxonomy.json`](./refusal_taxonomy.json).

## In-scope (factual FAQ)

Answer **only** when the information can be grounded in the corpus (after Phase 1–2 exist, via retrieval). Typical factual themes:

- Scheme attributes as presented on the AMC overview pages: expense ratio, exit load text, minimum SIP/lump sum, category, risk label, benchmark name if shown, lock-in for ELSS if shown.
- AMC-level facts if present on the page: address, incorporation dates, AUM figures as displayed.
- Process hints **only if** explicitly stated on these pages (e.g., links or copy about statements)—many topics may be **absent**; then respond with “not found in the provided sources,” not invention.

## Out-of-scope (refusal or no-data)

- **Advisory / suitability:** should I buy, how much to invest, timing, goals-based recommendations.
- **Comparisons:** which fund is better, ranking, “best” lists.
- **Performance opinions:** subjective quality, predictions, unless the question is strictly definitional and on-page (e.g., “what benchmark is stated”).
- **Returns / performance discussions** beyond neutral repetition of numbers **if** shown on page—no commentary; problem statement discourages comparisons and calculations.
- **Tax/legal advice** tailored to the individual.
- **Anything not on the five pages:** no hallucinated URLs or facts; state limitation clearly.

## Mixed queries

If a message combines factual and advisory parts (e.g., expense ratio + “should I buy?”), **default:** refuse the advisory intent or answer only the factual part if product policy explicitly allows splitting—document that policy in Phase 3 prompts.

## Corpus citation rule

Every **substantive factual answer** must cite **exactly one** URL from [`config/corpus_manifest.json`](../config/corpus_manifest.json). Refusal responses may use **educational** links from `refusal_taxonomy.json`, not extra corpus URLs.
