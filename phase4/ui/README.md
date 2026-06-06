# Phase 4 — Minimal user interface

Single-page chat UI per [PhaseWiseArchitecture.md](../../PhaseWiseArchitecture.md) §4.

## Features

- Welcome message and **three neutral example questions**
- Sticky disclaimer: **“Facts-only. No investment advice.”**
- Calls `POST /query` on the Phase 3 backend (same origin)
- Renders citation link, last-updated footer, and educational links when present
- Client-side PII rejection (PAN, Aadhaar, account-like numbers, email, phone, OTP)
- No form fields that collect personal identifiers

## Run end-to-end

From the project root:

```bash
python3 -m phase3.run_server
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

API endpoints remain available at `/query` and `/health`.

## Files

```
phase4/ui/
├── index.html      # Page structure
├── css/styles.css  # Layout and styling
└── js/app.js       # Chat logic and /query integration
```

The FastAPI server in `phase3/api/server.py` mounts this directory at `/`.

## Exit criteria

- User asks a question → sees answer or refusal
- Grounded answers show one citation URL and footer date
- Advisory/comparison refusals show an educational link
- Disclaimer visible without scrolling on desktop; sticky header on mobile
