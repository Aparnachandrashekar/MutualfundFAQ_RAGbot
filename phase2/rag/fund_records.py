"""Parse Groww AMC pages into per-fund structured records for chunking and extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TABLE_COLUMN_COUNT = 13
TABLE_HEADERS = (
    "Fund Name",
    "Category",
    "Risk",
    "NAV",
    "Expense Ratio",
    "1Y Returns",
    "3Y Returns",
    "5Y Returns",
    "7Y Returns",
    "10Y Returns",
    "Rating",
    "Fund Size (in Cr)",
    "Exit Load",
)

TABLE_END_MARKERS = (
    "View All",
    "Returns calculator",
    "Let's have a closer look",
    "View Mutual Funds from Other AMCs",
    "Explore all Mutual Funds on Groww",
)

DETAIL_BLOCK_PATTERN = re.compile(
    r"(?m)^([A-Z][^\n]+? Direct Growth)\s*$"
)


def _normalize_fund_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


_INVALID_SCHEME_WORDS = frozenset({
    "what", "is", "the", "of", "for", "tell", "me", "about", "nav", "aum",
    "how", "does", "do", "ratio", "expense", "minimum", "sip",
})


def is_valid_scheme_name(name: str) -> bool:
    words = set(re.findall(r"[a-z]+", name.lower()))
    if words & _INVALID_SCHEME_WORDS:
        return False
    return bool(re.search(r"\b(?:fund|fof|etf)\b", name, re.IGNORECASE))


def fund_name_matches(query_fund: str, record_fund: str) -> bool:
    """Match 'Union Midcap' to 'Union Midcap Fund' etc."""
    q = query_fund.lower().replace(" fund", "").strip()
    r = record_fund.lower().replace(" fund", "").strip()
    return q in r or r in q


def parse_scheme_table(text: str) -> list[dict[str, str]]:
    """Parse the 'List of … Mutual Fund in India' table into fund records."""
    marker = re.search(r"List of .+? Mutual Fund in India\s*\n", text)
    if not marker:
        return []

    rest = text[marker.end() :]
    end_pos = len(rest)
    for end_marker in TABLE_END_MARKERS:
        idx = rest.find(end_marker)
        if idx >= 0:
            end_pos = min(end_pos, idx)

    lines = [line.strip() for line in rest[:end_pos].splitlines() if line.strip()]
    try:
        header_idx = lines.index("Fund Name")
    except ValueError:
        return []

    data_lines = lines[header_idx + TABLE_COLUMN_COUNT :]
    records: list[dict[str, str]] = []

    i = 0
    while i + TABLE_COLUMN_COUNT <= len(data_lines):
        row = data_lines[i : i + TABLE_COLUMN_COUNT]
        fund_name = row[0]
        if not re.search(r"fund", fund_name, re.IGNORECASE):
            i += 1
            continue

        records.append(
            {
                "fund_name": _normalize_fund_name(fund_name),
                "category": row[1],
                "risk": row[2],
                "nav": row[3],
                "expense_ratio": row[4],
                "returns_1y": row[5],
                "returns_3y": row[6],
                "returns_5y": row[7],
                "returns_7y": row[8],
                "returns_10y": row[9],
                "rating": row[10],
                "fund_size_cr": row[11],
                "exit_load": row[12],
            }
        )
        i += TABLE_COLUMN_COUNT

    return records


def _format_fund_size_display(size_raw: str) -> str:
    val = size_raw.strip().lstrip("₹").strip()
    if not val or val.upper().startswith("NA"):
        return "NA"
    if val.lower().endswith("cr"):
        return f"₹{val}" if val.startswith("₹") else f"₹{val}"
    return f"₹{val} Cr"


def format_table_record(record: dict[str, str], amc_name: str) -> str:
    """Compact, retrieval-friendly text for one table row."""
    size_display = _format_fund_size_display(record.get("fund_size_cr", ""))

    parts = [
        f"{record['fund_name']} ({amc_name})",
        f"Category: {record['category']}",
        f"Risk: {record['risk']}",
        f"NAV: {record['nav']}",
        f"Expense Ratio: {record['expense_ratio']}",
        f"Fund Size (AUM): {size_display}",
        f"1Y Returns: {record['returns_1y']}",
    ]
    if record.get("returns_3y") and record["returns_3y"] not in ("--", "NA", "-"):
        parts.append(f"3Y Returns: {record['returns_3y']}")
    if record.get("returns_5y") and record["returns_5y"] not in ("--", "NA", "-"):
        parts.append(f"5Y Returns: {record['returns_5y']}")
    if record.get("rating") and record["rating"] not in ("--", "NA", "-"):
        parts.append(f"Rating: {record['rating']}")
    parts.append(f"Exit Load: {record['exit_load']}")
    return ". ".join(parts) + "."


def parse_scheme_detail_page(text: str) -> dict[str, str]:
    """Parse a single Groww scheme detail page into one fund record."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fund_name = ""
    if lines:
        title_match = re.match(r"^(.+?)\s+-\s+NAV,", lines[0], re.IGNORECASE)
        if title_match:
            fund_name = _normalize_fund_name(title_match.group(1))

    nav_m = re.search(r"NAV:\s*[^\n]+\n\s*(₹[\d,.]+)", text)
    expense_m = re.search(r"Expense ratio\s*\n\s*([\d.]+%)", text, re.IGNORECASE)
    aum_m = re.search(r"Fund size \(AUM\)\s*\n\s*(₹[^\n]+)", text, re.IGNORECASE)
    sip_m = re.search(r"Min\.\s*for SIP\s*\n\s*(₹[^\n]+)", text, re.IGNORECASE)
    rating_m = re.search(r"Rating\s*\n\s*(\d+)", text, re.IGNORECASE)
    exit_m = re.search(r"Exit load of ([^.]+\.)", text, re.IGNORECASE)
    about_m = re.search(r"is a\s+([^.]+?)\s+Mutual Fund Scheme", text, re.IGNORECASE)
    risk_m = re.search(r"is rated\s+([^.\n]+?)\s+risk", text, re.IGNORECASE)
    lump_m = re.search(r"Minimum Lumpsum Investment is\s+(₹[^\n.]+)", text, re.IGNORECASE)
    total_aum_m = re.search(r"Total AUM\s*\n\s*(₹[^\n]+)", text, re.IGNORECASE)

    returns_1y = returns_3y = returns_5y = ""
    fund_returns_m = re.search(
        r"Fund returns\s*\n\s*\+?([\d.]+%?)\s*\n\s*\+?([\d.]+%?)\s*\n\s*\+?([\d.]+%?)",
        text,
    )
    if fund_returns_m:
        returns_1y, returns_3y, returns_5y = fund_returns_m.groups()

    return {
        "fund_name": fund_name,
        "category": about_m.group(1).strip() if about_m else "",
        "risk": risk_m.group(1).strip() if risk_m else "",
        "nav": nav_m.group(1).strip() if nav_m else "",
        "expense_ratio": expense_m.group(1).strip() if expense_m else "",
        "fund_size_cr": aum_m.group(1).strip() if aum_m else "",
        "returns_1y": returns_1y,
        "returns_3y": returns_3y,
        "returns_5y": returns_5y,
        "returns_7y": "",
        "returns_10y": "",
        "rating": rating_m.group(1).strip() if rating_m else "",
        "exit_load": exit_m.group(1).strip() if exit_m else "",
        "detail_aum": total_aum_m.group(1).strip() if total_aum_m else "",
        "min_lump_sum": lump_m.group(1).strip() if lump_m else "",
        "min_sip": sip_m.group(1).strip() if sip_m else "",
        "min_investment_amt": "",
        "returns_3y_ann": "",
        "returns_5y_ann": "",
        "fund_manager": "",
    }


def parse_detail_blocks(text: str) -> list[dict[str, str]]:
    """Parse per-scheme detail blocks (… Direct Growth sections)."""
    closer = re.search(r"Let's have a closer look", text)
    if not closer:
        return []

    section = text[closer.start() :]
    for end_marker in TABLE_END_MARKERS[2:]:
        idx = section.find(end_marker)
        if idx > 0:
            section = section[:idx]

    matches = list(DETAIL_BLOCK_PATTERN.finditer(section))
    blocks: list[dict[str, str]] = []

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        block_text = section[start:end].strip()
        fund_title = match.group(1).strip()
        fund_name = fund_title.replace(" Direct Growth", "").strip()

        aum_match = re.search(r"AUM\s*\n\s*(₹[^\n]+|NA[^\n]*)", block_text, re.IGNORECASE)
        min_lump_match = re.search(
            r"Lump sum minimum amount for .+? is (₹[^\n.]+)",
            block_text,
            re.IGNORECASE,
        )
        min_sip_match = re.search(
            r"for SIP, it is (₹[^\n.]+)",
            block_text,
            re.IGNORECASE,
        )
        min_inv_match = re.search(
            r"Min Investment Amt\s*\n\s*(₹[^\n]+)",
            block_text,
            re.IGNORECASE,
        )
        returns_ann_match = re.search(
            r"annualized returns for the past 3 years & 5 years has been around ([\d.]+%?) & ([\d.]+%?)",
            block_text,
            re.IGNORECASE,
        )
        category_match = re.search(
            r"comes under the ([^.]+?) category of",
            block_text,
            re.IGNORECASE,
        )
        fund_manager_match = re.search(
            r"(?:Fund Manager|Managed by):\s*([^\n.]+)",
            block_text,
            re.IGNORECASE,
        )

        blocks.append(
            {
                "fund_name": fund_name,
                "fund_title": fund_title,
                "text": block_text,
                "aum": aum_match.group(1).strip() if aum_match else "",
                "min_lump_sum": min_lump_match.group(1).strip() if min_lump_match else "",
                "min_sip": min_sip_match.group(1).strip() if min_sip_match else "",
                "min_investment_amt": min_inv_match.group(1).strip() if min_inv_match else "",
                "returns_3y_ann": returns_ann_match.group(1).strip() if returns_ann_match else "",
                "returns_5y_ann": returns_ann_match.group(2).strip() if returns_ann_match else "",
                "detail_category": category_match.group(1).strip() if category_match else "",
                "fund_manager": fund_manager_match.group(1).strip() if fund_manager_match else "",
            }
        )

    return blocks


def format_detail_block(block: dict[str, str], amc_name: str) -> str:
    """Structured text for a scheme detail block."""
    parts = [f"{block['fund_title']} ({amc_name})."]
    if block.get("aum"):
        parts.append(f"AUM: {block['aum']}.")
    if block.get("min_lump_sum"):
        parts.append(f"Minimum lump sum: {block['min_lump_sum']}.")
    if block.get("min_sip"):
        parts.append(f"Minimum SIP: {block['min_sip']}.")
    return " ".join(parts)


def _find_matching_detail(
    fund_name: str,
    detail_blocks: list[dict[str, str]],
) -> dict[str, str] | None:
    for block in detail_blocks:
        if fund_name_matches(fund_name, block["fund_name"]):
            return block
    return None


def merge_fund_records(
    table_rows: list[dict[str, str]],
    detail_blocks: list[dict[str, str]],
    *,
    amc_name: str,
    source_id: str,
    source_url: str,
    ingested_at: str,
) -> list[dict[str, str]]:
    """Merge table rows and detail blocks into one structured record per scheme."""
    merged: list[dict[str, str]] = []
    matched_details: set[str] = set()

    for row in table_rows:
        detail = _find_matching_detail(row["fund_name"], detail_blocks)
        record: dict[str, str] = {
            **row,
            "amc_name": amc_name,
            "source_id": source_id,
            "source_url": source_url,
            "ingested_at": ingested_at,
            "fund_manager": "",
            "min_investment_amt": "",
            "returns_3y_ann": "",
            "returns_5y_ann": "",
            "detail_aum": "",
        }
        if detail:
            matched_details.add(detail["fund_name"])
            record.update({
                "detail_aum": detail.get("aum", ""),
                "min_lump_sum": detail.get("min_lump_sum", "") or record.get("min_lump_sum", ""),
                "min_sip": detail.get("min_sip", ""),
                "min_investment_amt": detail.get("min_investment_amt", ""),
                "returns_3y_ann": detail.get("returns_3y_ann", ""),
                "returns_5y_ann": detail.get("returns_5y_ann", ""),
                "fund_manager": detail.get("fund_manager", ""),
            })
            if detail.get("detail_category") and not record.get("category"):
                record["category"] = detail["detail_category"]

        merged.append(record)

    for detail in detail_blocks:
        if detail["fund_name"] in matched_details:
            continue
        if any(fund_name_matches(detail["fund_name"], r["fund_name"]) for r in merged):
            continue
        merged.append({
            "fund_name": detail["fund_name"],
            "fund_title": detail.get("fund_title", detail["fund_name"]),
            "category": detail.get("detail_category", ""),
            "risk": "",
            "nav": "",
            "expense_ratio": "",
            "returns_1y": "",
            "returns_3y": "",
            "returns_5y": "",
            "returns_7y": "",
            "returns_10y": "",
            "rating": "",
            "fund_size_cr": "",
            "exit_load": "",
            "amc_name": amc_name,
            "source_id": source_id,
            "source_url": source_url,
            "ingested_at": ingested_at,
            "detail_aum": detail.get("aum", ""),
            "min_lump_sum": detail.get("min_lump_sum", ""),
            "min_sip": detail.get("min_sip", ""),
            "min_investment_amt": detail.get("min_investment_amt", ""),
            "returns_3y_ann": detail.get("returns_3y_ann", ""),
            "returns_5y_ann": detail.get("returns_5y_ann", ""),
            "fund_manager": detail.get("fund_manager", ""),
        })

    return merged


def format_unified_fund_record(record: dict[str, str]) -> str:
    """Retrieval-friendly text with all stored fields for one scheme."""
    amc_name = record.get("amc_name", "")
    parts = [f"{record['fund_name']} ({amc_name})."]

    field_lines = [
        ("Category", record.get("category", "")),
        ("Risk", record.get("risk", "")),
        ("NAV", record.get("nav", "")),
        ("Expense Ratio", record.get("expense_ratio", "")),
        ("Fund Size (AUM)", _format_fund_size_display(record.get("fund_size_cr", ""))),
        ("Detail AUM", record.get("detail_aum", "")),
        ("1Y Returns", record.get("returns_1y", "")),
        ("3Y Returns", record.get("returns_3y", "")),
        ("5Y Returns", record.get("returns_5y", "")),
        ("7Y Returns", record.get("returns_7y", "")),
        ("10Y Returns", record.get("returns_10y", "")),
        ("3Y Annualized Returns", record.get("returns_3y_ann", "")),
        ("5Y Annualized Returns", record.get("returns_5y_ann", "")),
        ("Rating", record.get("rating", "")),
        ("Exit Load", record.get("exit_load", "")),
        ("Minimum lump sum", record.get("min_lump_sum", "")),
        ("Minimum SIP", record.get("min_sip", "")),
        ("Min Investment Amt", record.get("min_investment_amt", "")),
        ("Fund Manager", record.get("fund_manager", "")),
    ]

    for label, value in field_lines:
        val = (value or "").strip()
        if not val or val in ("--", "NA", "-", "N/A"):
            continue
        if label == "Fund Size (AUM)" and val == "NA" and record.get("detail_aum"):
            continue
        parts.append(f"{label}: {val}")

    return ". ".join(parts) + "."


def build_scheme_page_registry(
    text: str,
    *,
    amc_name: str,
    source_id: str,
    source_url: str,
    ingested_at: str,
) -> list[dict[str, str]]:
    """Build a single-scheme registry entry from a Groww scheme detail page."""
    record = parse_scheme_detail_page(text)
    if not record.get("fund_name"):
        return []
    record.update(
        amc_name=amc_name,
        source_id=source_id,
        source_url=source_url,
        ingested_at=ingested_at,
    )
    return [record]


def build_amc_fund_registry(
    text: str,
    *,
    amc_name: str,
    source_id: str,
    source_url: str,
    ingested_at: str,
) -> list[dict[str, str]]:
    """Build structured fund records for one AMC source page."""
    return merge_fund_records(
        parse_scheme_table(text),
        parse_detail_blocks(text),
        amc_name=amc_name,
        source_id=source_id,
        source_url=source_url,
        ingested_at=ingested_at,
    )


def build_corpus_fund_registry(corpus_run_dir: Path) -> list[dict[str, str]]:
    """Build structured fund records for all sources in a corpus run."""
    manifest_path = corpus_run_dir / "ingest_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_records: list[dict[str, str]] = []

    for source in manifest.get("sources", []):
        if not source.get("fetch_ok", False):
            continue
        source_id = source["id"]
        clean_path = corpus_run_dir / source_id / "clean.txt"
        if not clean_path.is_file():
            continue
        text = clean_path.read_text(encoding="utf-8")
        ingested_at = source.get("fetched_at_utc") or manifest.get("created_at_utc", "")
        registry_builder = (
            build_scheme_page_registry
            if source_id.startswith("groww_scheme_")
            else build_amc_fund_registry
        )
        all_records.extend(
            registry_builder(
                text,
                amc_name=source["amc_name"],
                source_id=source_id,
                source_url=source["canonical_url"],
                ingested_at=ingested_at,
            )
        )

    return all_records


def save_fund_registry(records: list[dict[str, str]], output_path: Path) -> Path:
    """Persist merged fund records to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fund_count": len(records),
        "source_amcs": sorted({r.get("amc_name", "") for r in records if r.get("amc_name")}),
        "fields": [
            "fund_name", "amc_name", "source_url", "category", "risk", "nav",
            "expense_ratio", "fund_size_cr", "detail_aum", "returns_1y",
            "returns_3y", "returns_5y", "returns_7y", "returns_10y",
            "returns_3y_ann", "returns_5y_ann", "rating", "exit_load",
            "min_lump_sum", "min_sip", "min_investment_amt", "fund_manager",
            "ingested_at",
        ],
        "funds": records,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def extract_amc_summary(text: str, amc_name: str) -> dict[str, str] | None:
    """Extract AMC-level summary (total AUM, scheme count)."""
    patterns = [
        (
            "total_aum",
            r"Total AUM \(as of end of last quarter\)\s*\n\s*(₹[^\n]+)",
        ),
        (
            "amc_aum",
            rf"{re.escape(amc_name)}\s*\nAUM\s*\n(₹[^\n]+)",
        ),
        (
            "scheme_count",
            r"No of Schemes\s*\n\s*(\d+)",
        ),
    ]

    summary: dict[str, str] = {"amc_name": amc_name}
    for key, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            summary[key] = match.group(1).strip()

    if len(summary) <= 1:
        return None
    return summary


def format_amc_summary(summary: dict[str, str]) -> str:
    amc = summary["amc_name"]
    parts = [f"{amc} overview."]
    if summary.get("total_aum"):
        parts.append(f"Total AUM: {summary['total_aum']}.")
    elif summary.get("amc_aum"):
        parts.append(f"Total AUM: {summary['amc_aum']}.")
    if summary.get("scheme_count"):
        parts.append(f"Number of schemes: {summary['scheme_count']}.")
    return " ".join(parts)


def detect_query_metric(query: str) -> str | None:
    q = query.lower()
    metrics = [
        ("nav", ("nav", "net asset value")),
        ("aum", ("aum", "assets under management", "fund size")),
        ("expense_ratio", ("expense ratio",)),
        ("exit_load", ("exit load",)),
        ("sip", ("sip", "systematic investment", "minimum sip")),
        ("minimum_investment", ("minimum investment", "minimum lump", "min investment")),
        ("returns", ("returns", "1y returns", "performance")),
        ("category", ("category", "fund type")),
        ("risk", ("risk", "riskometer")),
        ("rating", ("rating", "crisil rating")),
        ("fund_manager", ("fund manager", "who manages", "who is the manager", "managed by")),
    ]
    for metric, keywords in metrics:
        if any(kw in q for kw in keywords):
            return metric
    return None


def is_out_of_domain_query(query: str) -> bool:
    """Reject clearly irrelevant queries before retrieval."""
    q = query.lower()
    off_topic = (
        "weather", "temperature", "cricket", "football", "movie", "recipe",
        "stock price", "bitcoin", "crypto", "politics", "election",
        "who is the president", "capital of",
    )
    mf_signals = (
        "mutual fund", "nav", "aum", "sip", "elss", "expense ratio", "exit load",
        "scheme", "amc", "groww", "choice", "unifi", "union", "icici", "lic",
        "fund", "investment amount", "benchmark",
    )
    if any(signal in q for signal in mf_signals):
        return False
    return any(topic in q for topic in off_topic)


# Corpus scope — six indexed Groww scheme pages
CORPUS_AMC_ALIASES: frozenset[str] = frozenset({
    "hdfc", "sbi", "bandhan", "quant", "parag parikh", "ppfas",
})

OUT_OF_CORPUS_AMC_ALIASES: frozenset[str] = frozenset({
    "choice", "unifi", "union", "icici", "icici prudential", "lic",
    "axis", "kotak", "nippon", "mirae", "dsp", "franklin",
    "tata mutual", "tata", "aditya birla", "birla sun life", "pgim",
    "motilal", "hsbc", "baroda", "boi", "invesco",
    "edelweiss", "samco", "nj mutual", "whiteoak",
    "capitalmind", "jio", "uti", "mahindra", "canara", "sundaram",
    "quantum", "bank of india", "taurus", "trust mf", "groww mf",
})

FUND_CATEGORY_TERMS: frozenset[str] = frozenset({
    "mid cap", "midcap", "large cap", "large & mid cap", "large and mid cap",
    "small cap", "flexi cap", "multi cap", "elss", "liquid fund", "debt fund",
    "hybrid fund", "index fund", "large cap fund",
})

_AMC_OVERVIEW_PATTERN = re.compile(
    r"\b(aum|nav|assets under management|net asset value|total aum)\b",
    re.IGNORECASE,
)

_CORPUS_SCHEME_NAMES: frozenset[str] | None = None


def _default_chunks_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "phase2_results" / "chunks" / "chunks.json"


def _load_corpus_scheme_names() -> frozenset[str]:
    global _CORPUS_SCHEME_NAMES
    if _CORPUS_SCHEME_NAMES is not None:
        return _CORPUS_SCHEME_NAMES

    names: set[str] = set()
    chunks_path = _default_chunks_path()
    if chunks_path.is_file():
        for chunk in json.loads(chunks_path.read_text(encoding="utf-8")):
            text = chunk.get("text", "")
            if "overview" in text.lower():
                continue
            first = text.split(".", 1)[0].strip()
            label = first.split("(")[0].strip()
            if is_valid_scheme_name(label):
                names.add(label)
            for match in re.finditer(
                r"^([A-Z][A-Za-z0-9& ]+?(?:Index Fund|Fund))(?:\s*\(|\s+Direct Growth|\.)",
                text,
                re.MULTILINE,
            ):
                candidate = match.group(1).strip()
                if is_valid_scheme_name(candidate):
                    names.add(candidate)

    _CORPUS_SCHEME_NAMES = frozenset(names)
    return _CORPUS_SCHEME_NAMES


def is_known_corpus_scheme(name: str) -> bool:
    """Return True when the scheme name exists in the indexed corpus."""
    known = _load_corpus_scheme_names()
    if not known:
        return bool(mentions_corpus_amc(name))
    return any(fund_name_matches(name, candidate) for candidate in known)


def _query_contains_alias(query_lower: str, alias: str) -> bool:
    if " " in alias:
        return alias in query_lower
    return bool(re.search(rf"\b{re.escape(alias)}\b", query_lower))


def mentions_out_of_corpus_amc(query: str) -> bool:
    """True when the query names an AMC outside the indexed scheme corpus."""
    q = query.lower()
    return any(_query_contains_alias(q, alias) for alias in OUT_OF_CORPUS_AMC_ALIASES)


def mentions_corpus_amc(query: str) -> bool:
    q = query.lower()
    return any(_query_contains_alias(q, alias) for alias in CORPUS_AMC_ALIASES)


SCHEME_SPECIFIC_METRICS: frozenset[str] = frozenset({
    "expense_ratio", "exit_load", "sip", "minimum_investment", "returns", "category",
    "risk", "rating", "fund_manager",
})

UNSUPPORTED_CORPUS_METRICS: frozenset[str] = frozenset()


def is_query_in_corpus_scope(
    query: str,
    *,
    fund_names: list[str] | None = None,
) -> bool:
    """
    Return False when the query cannot be grounded in the indexed scheme corpus.

    In scope when a named indexed scheme is referenced, or when a corpus AMC
    is referenced together with a supported factual metric.
    """
    if mentions_out_of_corpus_amc(query):
        return False

    if fund_names:
        if any(mentions_out_of_corpus_amc(name) for name in fund_names):
            return False
        return all(is_known_corpus_scheme(name) for name in fund_names)

    if mentions_corpus_amc(query):
        if detect_query_metric(query) and detect_query_metric(query) not in UNSUPPORTED_CORPUS_METRICS:
            return True
        return bool(_AMC_OVERVIEW_PATTERN.search(query))

    q = query.lower()
    if any(term in q for term in FUND_CATEGORY_TERMS):
        return False

    if detect_query_metric(query):
        return False

    return False


def requires_named_scheme(query: str, metric: str | None, fund_names: list[str]) -> bool:
    """
    Return True when the query asks for a per-scheme metric but does not name a scheme.

    Exceptions: AMC total AUM (overview) and AMC-level NAV listing.
    """
    if not metric or fund_names:
        return False
    if not mentions_corpus_amc(query):
        return True
    if metric in ("aum", "nav"):
        return False
    if metric in SCHEME_SPECIFIC_METRICS:
        return True
    return False
