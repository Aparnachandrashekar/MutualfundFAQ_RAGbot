"""Structured fact extraction from retrieved chunks aligned with user queries."""

from __future__ import annotations

import re
from typing import Any

from phase2.rag.fund_records import (
    detect_query_metric,
    fund_name_matches,
    is_out_of_domain_query,
    is_query_in_corpus_scope,
    is_valid_scheme_name,
    is_known_corpus_scheme,
    mentions_corpus_amc,
    requires_named_scheme,
    schemes_for_corpus_amc_query,
)

_SCHEME_NAMES_CACHE: list[str] | None = None


def _load_scheme_names() -> list[str]:
    """Known scheme names from indexed chunks (longest first for matching)."""
    global _SCHEME_NAMES_CACHE
    if _SCHEME_NAMES_CACHE is not None:
        return _SCHEME_NAMES_CACHE

    from phase3.generation.config import PHASE2_DIR

    names: set[str] = set()
    chunks_path = PHASE2_DIR / "chunks" / "chunks.json"
    if chunks_path.is_file():
        import json

        for chunk in json.loads(chunks_path.read_text(encoding="utf-8")):
            if "overview" in chunk.get("text", "").lower():
                continue
            for name in _chunk_fund_names(chunk):
                if "overview" not in name.lower():
                    names.add(name)

    _SCHEME_NAMES_CACHE = sorted(names, key=len, reverse=True)
    return _SCHEME_NAMES_CACHE


def _match_known_scheme(text: str) -> str | None:
    """Case-insensitive match against indexed scheme names."""
    text_l = text.lower().strip().rstrip("?.!")
    for name in _load_scheme_names():
        name_l = name.lower()
        if name_l == text_l or name_l in text_l or text_l in name_l:
            return name
        core = name_l.removesuffix(" index fund").removesuffix(" fund")
        if core and (core in text_l or text_l in core):
            return name
    return None


def resolve_query_fund_names(query: str) -> list[str]:
    """Resolve scheme names, including unambiguous AMC-only queries."""
    names = extract_fund_names_from_query(query)
    if names:
        if all(is_known_corpus_scheme(name) for name in names):
            return names
        amc_schemes = schemes_for_corpus_amc_query(query)
        if len(amc_schemes) == 1:
            return [amc_schemes[0]]
        return names

    focus = query.strip().rstrip("?.!")
    for marker in (" about ", " for ", " of "):
        idx = focus.lower().rfind(marker)
        if idx >= 0:
            focus = focus[idx + len(marker):].strip()
            break

    known = _match_known_scheme(focus)
    if known:
        amc_schemes = schemes_for_corpus_amc_query(query)
        if len(amc_schemes) <= 1:
            return [known]

    amc_schemes = schemes_for_corpus_amc_query(query)
    if len(amc_schemes) == 1:
        return [amc_schemes[0]]
    return []


def extract_fund_names_from_query(query: str) -> list[str]:
    """Extract scheme names from the query (excluding AMC names)."""
    amc_names = {
        "choice mutual fund", "unifi mutual fund", "union mutual fund",
        "icici prudential mutual fund", "lic mutual fund",
        "hdfc mutual fund", "sbi mutual fund", "bandhan mutual fund",
        "quant mutual fund", "parag parikh mutual fund", "ppfas mutual fund",
    }

    focus = query.strip().rstrip("?.!")
    for marker in (" about ", " for ", " of "):
        idx = focus.lower().rfind(marker)
        if idx >= 0:
            focus = focus[idx + len(marker):].strip()
            break

    word = r"[A-Z0-9][A-Za-z0-9&]*"
    tail = rf"(?:\s+(?:&\s+|and\s+)?(?:[0-9]+|{word}))*"
    patterns = [
        rf"\b({word}{tail}\s+Index\s+Fund)\b",
        rf"\b({word}{tail}\s+Fund)\b",
        rf"\b({word}(?:\s+{word})+)\s+Direct Growth\b",
    ]

    candidates: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, focus):
            name = match.group(1).strip()
            if name.lower() in amc_names:
                continue
            if is_valid_scheme_name(name):
                candidates.append(name)

    if not candidates:
        return []

    candidates.sort(key=len, reverse=True)
    return [candidates[0]]


def _is_valid_nav(value: str) -> bool:
    value = value.strip().lstrip("₹").replace(",", "")
    if not value or value in ("--", "NA", "-", "N/A"):
        return False
    return bool(re.match(r"^[\d.]+$", value))


def _is_valid_aum(value: str) -> bool:
    value = value.strip()
    if not value or value.upper().startswith("NA"):
        return False
    return "₹" in value or re.search(r"\d", value)


def _chunk_fund_names(chunk: dict[str, Any]) -> list[str]:
    text = chunk.get("text", "")
    names: list[str] = []
    for match in re.finditer(
        r"^([A-Z][A-Za-z0-9& ]+?(?:Index Fund|Fund))(?:\s*\(|\s+Direct Growth|\.)",
        text,
        re.MULTILINE,
    ):
        candidate = match.group(1).strip()
        if is_valid_scheme_name(candidate):
            names.append(candidate)
    if not names:
        first = text.split(".", 1)[0].strip()
        if is_valid_scheme_name(first):
            names.append(first.split("(")[0].strip())
    return list(dict.fromkeys(names))


def _resolve_fund_label(
    chunk: dict[str, Any],
    fund_names: list[str],
) -> str | None:
    """Prefer the canonical scheme name from the matched chunk."""
    candidates = _chunk_fund_names(chunk)
    if fund_names:
        for candidate in candidates:
            if any(fund_name_matches(qf, candidate) for qf in fund_names):
                return candidate
    for name in candidates:
        if "overview" not in name.lower():
            return name
    return candidates[0] if candidates else None


def _chunk_matches_fund(chunk: dict[str, Any], fund_names: list[str]) -> bool:
    if not fund_names:
        return True
    text = chunk.get("text", "")
    candidates = _chunk_fund_names(chunk)
    return any(
        fund_name_matches(qf, candidate) or fund_name_matches(qf, text)
        for qf in fund_names
        for candidate in candidates
    )


def _format_aum_value(raw: str) -> str:
    val = raw.strip()
    if val.startswith("₹"):
        return val if "cr" in val.lower() else f"{val} Cr"
    return f"₹{val} Cr"


def _extracted_value_in_chunk(fields: dict[str, str], metric: str, chunk_text: str) -> bool:
    """Ensure parsed numeric values appear in the source chunk (anti-hallucination)."""
    key_map = {
        "nav": "nav",
        "expense_ratio": "expense_ratio",
        "aum": "aum",
        "total_aum": "total_aum",
        "sip": "min_sip",
        "minimum_investment": "min_lump_sum",
        "returns": "returns_1y",
    }
    field_key = key_map.get(metric, "")
    if not field_key:
        return True
    value = fields.get(field_key, "")
    if not value:
        return metric == "minimum_investment" and bool(fields.get("min_sip"))
    normalized_chunk = chunk_text.replace(",", "")
    normalized_value = value.replace(",", "").lstrip("₹")
    return normalized_value in normalized_chunk.replace("₹", "")


def _parse_table_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    patterns = {
        "nav": r"NAV:\s*₹?([\d.,]+)",
        "aum": r"Fund Size \(AUM\):\s*(₹[\d.,]+\s*Cr?)",
        "detail_aum": r"Detail AUM:\s*(₹[^\s\n]+|NA[^\s\n]*)",
        "expense_ratio": r"Expense Ratio:\s*([\d.]+%?)",
        "exit_load": r"Exit Load:\s*([^.\n]+(?:\.[^.\n]+)?)",
        "min_sip": r"Minimum SIP:\s*(₹[^\s.]+(?:\.[^\s.]+)?)",
        "min_lump_sum": r"Minimum lump sum:\s*(₹[^\s.]+(?:\.[^\s.]+)?)",
        "min_investment_amt": r"Min Investment Amt:\s*(₹[^\s.]+(?:\.[^\s.]+)?)",
        "category": r"Category:\s*([^.\n]+)",
        "risk": r"Risk:\s*([^.\n]+)",
        "rating": r"Rating:\s*([^.\n]+)",
        "returns_1y": r"1Y Returns:\s*([^.\n]+)",
        "returns_3y": r"3Y Returns:\s*([^.\n]+)",
        "returns_5y": r"5Y Returns:\s*([^.\n]+)",
        "returns_3y_ann": r"3Y Annualized Returns:\s*([^.\n]+)",
        "returns_5y_ann": r"5Y Annualized Returns:\s*([^.\n]+)",
        "fund_manager": r"Fund Manager:\s*([^.\n]+)",
        "total_aum": r"Total AUM:\s*(₹[\d.,]+\s*Cr?)",
        "block_aum": r"AUM:\s*(₹[^\s\n]+|NA[^\s\n]*)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            fields[key] = match.group(1).strip()
    if "aum" not in fields and fields.get("detail_aum"):
        fields["aum"] = fields["detail_aum"]
    if "aum" not in fields and fields.get("block_aum"):
        fields["aum"] = fields["block_aum"]
    return fields


def extract_fact_from_chunk(
    chunk: dict[str, Any],
    query: str,
    metric: str | None = None,
    fund_names: list[str] | None = None,
) -> str | None:
    """Extract a concise answer for the requested metric from one chunk."""
    metric = metric or detect_query_metric(query)
    if not metric:
        return None

    fund_names = fund_names if fund_names is not None else resolve_query_fund_names(query)
    if requires_named_scheme(query, metric, fund_names):
        return None

    text = chunk.get("text", "")

    if fund_names and not _chunk_matches_fund(chunk, fund_names):
        return None

    fields = _parse_table_fields(text)
    amc_name = chunk.get("amc_name", "the AMC")
    fund_label = _resolve_fund_label(chunk, fund_names)

    if metric == "nav":
        nav = fields.get("nav", "").lstrip("₹").strip()
        if _is_valid_nav(nav) and fund_label and _extracted_value_in_chunk(fields, "nav", text):
            display = nav if fields.get("nav", "").startswith("₹") else f"₹{nav}"
            return f"The NAV of {fund_label} is {display}."
        return None

    if metric == "aum":
        if fund_names and fields.get("aum") and _is_valid_aum(fields["aum"]) and fund_label:
            if _chunk_matches_fund(chunk, fund_names) and _extracted_value_in_chunk(fields, "aum", text):
                if "overview" in text.lower() or fields["aum"].upper().startswith("NA"):
                    return None
                return f"The AUM (fund size) of {fund_label} is {_format_aum_value(fields['aum'])}."
        if not fund_names:
            total = fields.get("total_aum", "")
            if total and _is_valid_aum(total) and _extracted_value_in_chunk(fields, "total_aum", text):
                return f"The total AUM of {amc_name} is {total}."
        return None

    if metric == "expense_ratio" and fields.get("expense_ratio") and fund_label:
        if _extracted_value_in_chunk(fields, "expense_ratio", text):
            return f"The expense ratio of {fund_label} is {fields['expense_ratio']}."
        return None

    if metric == "exit_load" and fields.get("exit_load") and fund_label:
        if fields["exit_load"] in text:
            return f"The exit load for {fund_label} is {fields['exit_load']}."
        return None

    if metric == "sip" and fields.get("min_sip") and fund_label:
        if fields["min_sip"] in text:
            return f"The minimum SIP for {fund_label} is {fields['min_sip']}."
        return None

    if metric == "minimum_investment":
        if fields.get("min_lump_sum") and fund_label and fields["min_lump_sum"] in text:
            return f"The minimum lump sum investment for {fund_label} is {fields['min_lump_sum']}."
        if fields.get("min_sip") and fund_label and fields["min_sip"] in text:
            return f"The minimum SIP for {fund_label} is {fields['min_sip']}."
        return None

    if metric == "returns" and fund_label:
        q = query.lower()
        if "3" in q:
            val = fields.get("returns_3y_ann") or fields.get("returns_3y", "")
        elif "5" in q:
            val = fields.get("returns_5y_ann") or fields.get("returns_5y", "")
        else:
            val = fields.get("returns_1y", "")
        if val and val not in ("--", "NA", "-") and val in text:
            period = "3-year" if "3" in q else "5-year" if "5" in q else "1-year"
            return f"The {period} returns for {fund_label} are {val}."
        return None

    if metric == "category" and fields.get("category") and fund_label:
        if fields["category"] in text:
            return f"{fund_label} is categorized as {fields['category']}."
        return None

    if metric == "risk" and fields.get("risk") and fund_label:
        if fields["risk"] in text:
            return f"The risk level of {fund_label} is {fields['risk']}."
        return None

    if metric == "rating" and fields.get("rating") and fund_label:
        if fields["rating"] in text:
            return f"The rating of {fund_label} is {fields['rating']}."
        return None

    if metric == "fund_manager" and fields.get("fund_manager") and fund_label:
        if fields["fund_manager"] in text:
            return f"The fund manager of {fund_label} is {fields['fund_manager']}."
        return None

    return None


def chunk_supports_query(
    chunk: dict[str, Any],
    query: str,
    metric: str | None = None,
    fund_names: list[str] | None = None,
) -> bool:
    """Return True when the chunk contains an extractable answer for the query."""
    if is_out_of_domain_query(query):
        return False

    if not is_query_in_corpus_scope(query, fund_names=fund_names):
        return False

    metric = metric or detect_query_metric(query)
    fund_names = fund_names if fund_names is not None else resolve_query_fund_names(query)

    if metric and fund_names:
        return extract_fact_from_chunk(chunk, query, metric=metric, fund_names=fund_names) is not None

    if metric == "nav" and not fund_names:
        fields = _parse_table_fields(chunk.get("text", ""))
        return _is_valid_nav(fields.get("nav", ""))

    if metric == "aum" and not fund_names:
        text = chunk.get("text", "")
        fields = _parse_table_fields(text)
        if "overview" in text.lower() and _is_valid_aum(fields.get("total_aum", "")):
            return True
        return False

    if metric and requires_named_scheme(query, metric, fund_names):
        return False

    if metric:
        return extract_fact_from_chunk(chunk, query, metric=metric, fund_names=fund_names) is not None

    text = chunk.get("text", "")
    overlap_terms = _query_terms_simple(query)
    return bool(overlap_terms) and sum(1 for t in overlap_terms if t in text.lower()) >= 2


def _query_terms_simple(query: str) -> set[str]:
    stop = {"what", "is", "the", "of", "tell", "me", "about", "for", "a", "an"}
    return {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in stop and len(w) > 2}


def build_answer_from_chunks(
    chunks: list[dict[str, Any]],
    query: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Pick the best chunk and extract a structured factual answer."""
    metric = detect_query_metric(query)
    fund_names = resolve_query_fund_names(query)

    if requires_named_scheme(query, metric, fund_names):
        return None, None

    ranked = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)

    if fund_names or metric not in ("nav", "aum"):
        for chunk in ranked:
            if not chunk_supports_query(chunk, query, metric=metric, fund_names=fund_names):
                continue
            answer = extract_fact_from_chunk(
                chunk, query, metric=metric, fund_names=fund_names
            )
            if answer:
                return answer, chunk
        return None, None

    if metric == "aum":
        for chunk in ranked:
            if "overview" in chunk.get("text", "").lower():
                answer = extract_fact_from_chunk(chunk, query, metric="aum", fund_names=[])
                if answer:
                    return answer, chunk
        for chunk in ranked:
            answer = extract_fact_from_chunk(chunk, query, metric="aum", fund_names=[])
            if answer:
                return answer, chunk

    if metric == "nav":
        nav_lines: list[str] = []
        source_chunk = None
        target_amc = None
        if mentions_corpus_amc(query):
            for alias in ("choice", "unifi", "union", "icici prudential", "lic"):
                if alias in query.lower():
                    from phase2.rag.config import AMC_ALIASES
                    target_amc = AMC_ALIASES.get(alias, "")
                    break
        for chunk in ranked:
            if target_amc and chunk.get("amc_name") != target_amc:
                continue
            fields = _parse_table_fields(chunk.get("text", ""))
            nav = fields.get("nav", "")
            if not _is_valid_nav(nav):
                continue
            names = _chunk_fund_names(chunk)
            fund_label = names[0] if names else None
            if not fund_label:
                continue
            nav_lines.append(f"{fund_label} has NAV {nav}")
            source_chunk = source_chunk or chunk
            if len(nav_lines) >= 2:
                break
        if nav_lines and source_chunk:
            return ". ".join(nav_lines[:2]) + ".", source_chunk

    return None, None
