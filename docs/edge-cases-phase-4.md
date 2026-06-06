# Edge cases — Phase 4 (Minimal user interface)

Companion to **Phase 4** in [`PhaseWiseArchitecture.md`](../PhaseWiseArchitecture.md).

Scope: welcome + **three** example questions; disclaimer **“Facts-only. No investment advice.”**; no PII collection; `/query` to backend.

---

## Input and privacy

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| User pastes PAN, Aadhaar, bank account, OTP in chat | Violates Problemstatement | **Reject** input with fixed message; do not echo PII; optionally discard message server-side without logging content. |
| User enters email/phone for “support” | Same | No fields requesting them; if pasted, same as above. |
| Long pasted legal text or spam | DoS / cost | Max input length; truncate or block with friendly error. |

---

## UX and comprehension

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Disclaimer below fold on mobile | User misses facts-only scope | Sticky short disclaimer or modal on first send; example questions reinforce neutral tone. |
| Three example questions imply endorsement | Feels like “recommended asks” | Use **neutral** factual prompts (expense ratio, exit load, min SIP)—not “Should I invest?” |
| User cannot click citation (plain text URL) | Weak verifiability | Render citation as **accessible link**; open in new tab with `rel="noopener noreferrer"`. |
| Answer overflows screen; footer date off-screen | User misses “last updated” | Scrollable transcript; keep footer visible or repeat date in metadata line. |

---

## Reliability and errors

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Backend timeout / 5xx | Blank UI frustration | Show retry + non-alarming copy; do not expose stack traces. |
| Streaming partial tokens show unsafe draft | Rare flash of bad content | If streaming, buffer until citation validated—or stream only after retrieval gate passes. |
| Rate limiting / abuse | Cost and stability | Per-IP or per-session limits; CAPTCHA only if product allows (avoid collecting PII). |

---

## Accessibility

| Edge case | Why it matters | Suggested handling |
|-----------|----------------|-------------------|
| Screen reader skips disclaimer | Compliance gap | Landmark region + `aria` for disclaimer; logical heading order. |
| Color-only risk indicators | Inaccessible | Do not rely on color alone for warnings; use text. |

---

## Review checklist (Phase 4 exit)

- [ ] Disclaimer always visible per design target (including mobile).
- [ ] No form fields collect restricted identifiers.
- [ ] Error and “no sources” states are user-tested once.
