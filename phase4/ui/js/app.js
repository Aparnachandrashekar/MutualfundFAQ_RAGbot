/**
 * Phase 4 — Chat UI for Mutual Fund FAQ Assistant.
 * Calls POST /query on the same origin. No PII collection.
 */

const MAX_QUERY_LENGTH = 2000;

function apiUrl(path) {
  const base = (window.API_BASE || "").replace(/\/$/, "");
  return base ? `${base}${path}` : path;
}

const API_QUERY_URL = apiUrl("/query");
const API_TIMEOUT_MS = 120000;

const REFUSAL_TYPES = new Set([
  "refusal_advisory",
  "refusal_comparison",
  "refusal_personal_info",
]);

const PII_MESSAGE =
  "For your privacy, please do not enter PAN, Aadhaar, account numbers, OTPs, email, or phone numbers. Ask a general factual question instead.";

const PII_PATTERNS = [
  /\b[A-Z]{5}[0-9]{4}[A-Z]\b/i,
  /\b[0-9]{4}\s?[0-9]{4}\s?[0-9]{4}\b/,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,
  /\b(?:\+91[\s-]?)?[6-9]\d{9}\b/,
  /\b(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}\b/,
  /\b(?:otp|one[-\s]?time\s+password)\b.*\b\d{4,8}\b/i,
  /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/,
];

const BOT_AVATAR_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
  <rect x="5" y="8" width="14" height="11" rx="2"/>
  <circle cx="9.5" cy="13" r="1.25" fill="currentColor" stroke="none"/>
  <circle cx="14.5" cy="13" r="1.25" fill="currentColor" stroke="none"/>
  <path d="M12 3v3M8 5l1.5 2M16 5l-1.5 2"/>
</svg>`;

const DOC_ICON_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
  <polyline points="14 2 14 8 20 8"/>
  <line x1="8" y1="13" x2="16" y2="13"/>
  <line x1="8" y1="17" x2="13" y2="17"/>
</svg>`;

const chatEl = document.getElementById("chat");
const mainEl = document.querySelector(".main");
const welcomeEl = document.getElementById("welcome");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const corpusUpdatedNote = document.getElementById("corpus-updated-note");

function containsPii(text) {
  return PII_PATTERNS.some((pattern) => pattern.test(text));
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function citationDisplayName(url) {
  const slug = url.split("/").filter(Boolean).pop() || "";
  const names = {
    "hdfc-silver-etf-fof-direct-growth": "HDFC Silver ETF FoF Direct Growth",
    "hdfc-mid-cap-fund-direct-growth": "HDFC Mid Cap Fund Direct Growth",
    "parag-parikh-long-term-value-fund-direct-growth": "Parag Parikh Long Term Value Fund Direct Growth",
    "bandhan-small-cap-fund-direct-growth": "Bandhan Small Cap Fund Direct Growth",
    "quant-small-cap-fund-direct-plan-growth": "Quant Small Cap Fund Direct Plan Growth",
    "sbi-gold-fund-direct-growth": "SBI Gold Direct Plan Growth",
  };
  if (names[slug]) return names[slug];
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function syncDateFromFooter(footer) {
  if (!footer) return "";
  const match = footer.match(/(\d{4}-\d{2}-\d{2})/);
  return match ? `SYNC: ${match[1]}` : footer.replace(/^Last updated from sources:\s*/i, "SYNC: ");
}

function formatCorpusDate(isoDate) {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return null;
  const [year, month, day] = isoDate.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function corpusUpdatedLabel(isoDate) {
  const formatted = formatCorpusDate(isoDate);
  if (!formatted) return null;
  return `Data updated as of ${formatted}.`;
}

async function loadCorpusUpdatedNote() {
  if (!corpusUpdatedNote) return;

  let isoDate = null;

  try {
    const metaResponse = await fetch("/data/corpus-meta.json");
    if (metaResponse.ok) {
      const meta = await metaResponse.json();
      isoDate = meta.data_as_of || null;
    }
  } catch {
    /* try health fallback */
  }

  if (!isoDate) {
    try {
      const healthResponse = await fetch(apiUrl("/health"));
      if (healthResponse.ok) {
        const data = await healthResponse.json();
        isoDate = data.corpus_last_updated || null;
      }
    } catch {
      /* keep placeholder */
    }
  }

  const label = corpusUpdatedLabel(isoDate);
  if (label) {
    corpusUpdatedNote.textContent = label;
  }
}

function createMessageRow(role, innerHtml, extraClass = "") {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.innerHTML = BOT_AVATAR_SVG;
    row.appendChild(avatar);
  }

  const article = document.createElement("article");
  article.className = `message ${role}${extraClass ? ` ${extraClass}` : ""}`;
  article.innerHTML = innerHtml;
  row.appendChild(article);

  chatEl.appendChild(row);
  scrollChatToBottom();
  return row;
}

function scrollChatToBottom() {
  if (!mainEl) return;
  mainEl.scrollTo({ top: mainEl.scrollHeight, behavior: "smooth" });
}

function renderBotResponse(data) {
  const isRefusal = REFUSAL_TYPES.has(data.response_type);
  let html = "";

  if (isRefusal) {
    html += `<div class="refusal-banner" role="status">🚫 Non-advisory response</div>`;
  }

  html += `<p class="message-text">${escapeHtml(data.response)}</p>`;

  if (data.citation) {
    const title = citationDisplayName(data.citation);
    const sync = syncDateFromFooter(data.footer || "");
    html += `
      <div class="citation-card">
        <span class="citation-card-icon">${DOC_ICON_SVG}</span>
        <div class="citation-card-body">
          <p class="citation-card-title">
            <a href="${escapeHtml(data.citation)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}</a>
          </p>
          ${sync ? `<p class="citation-card-sync">${escapeHtml(sync)}</p>` : ""}
        </div>
      </div>`;
  } else if (data.footer && !isRefusal) {
    html += `<p class="citation-card-sync" style="margin-top:0.65rem">${escapeHtml(data.footer)}</p>`;
  }

  if (data.educational_link) {
    html += `<p class="educational-link"><strong>Learn more:</strong> <a href="${escapeHtml(data.educational_link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(data.educational_link)}</a></p>`;
  }

  return html;
}

function typingHtml() {
  return `<p class="message-text">Thinking<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span></p>`;
}

async function submitQuery(query) {
  const trimmed = query.trim();
  if (!trimmed) return;

  if (trimmed.length > MAX_QUERY_LENGTH) {
    createMessageRow(
      "bot",
      `<p class="message-text">Your question is too long. Please keep it under ${MAX_QUERY_LENGTH} characters.</p>`,
      "error"
    );
    return;
  }

  if (containsPii(trimmed)) {
    createMessageRow("bot", `<p class="message-text">${escapeHtml(PII_MESSAGE)}</p>`, "error");
    return;
  }

  welcomeEl.hidden = true;

  createMessageRow("user", `<p class="message-text">${escapeHtml(trimmed)}</p>`);
  inputEl.value = "";
  sendBtn.disabled = true;

  const typingRow = createMessageRow("bot", typingHtml());

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

    const response = await fetch(API_QUERY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: trimmed }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }

    const data = await response.json();
    typingRow.querySelector(".message").outerHTML =
      `<article class="message bot">${renderBotResponse(data)}</article>`;
    scrollChatToBottom();
  } catch (err) {
    const isTimeout = err && err.name === "AbortError";
    const message = isTimeout
      ? "The server is taking too long to respond. If this is the first question after a while, the API may be waking up — wait a minute and try again."
      : "Something went wrong while fetching an answer. Please try again in a moment.";
    typingRow.querySelector(".message").outerHTML =
      `<article class="message bot error"><p class="message-text">${escapeHtml(message)}</p></article>`;
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuery(inputEl.value);
});

document.querySelectorAll(".example-btn").forEach((button) => {
  button.addEventListener("click", () => {
    const query = button.dataset.query || "";
    inputEl.value = query;
    submitQuery(query);
  });
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 96)}px`;
});

loadCorpusUpdatedNote();
