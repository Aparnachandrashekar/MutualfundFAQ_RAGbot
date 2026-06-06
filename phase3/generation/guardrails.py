#!/usr/bin/env python3
"""
Phase 3 — Response guardrails and safety checks.

Ensures responses comply with safety requirements:
- Facts-only answers without investment advice
- No URLs when answer is unknown or query involves personal information
- Proper citation handling only for grounded factual answers
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .config import (
    ALLOWED_CITATION_URLS,
    EDUCATIONAL_LINKS,
    MAX_CHARS_PER_SENTENCE,
    MAX_SENTENCES,
    NO_ANSWER_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    REFUSAL_TAXONOMY_PATH,
)


class ResponseType(str, Enum):
    ANSWER_WITH_CITATION = "answer_with_citation"
    ANSWER_NO_CITATION = "answer_no_citation"
    REFUSAL_ADVISORY = "refusal_advisory"
    REFUSAL_COMPARISON = "refusal_comparison"
    REFUSAL_PERSONAL_INFO = "refusal_personal_info"
    NO_INFORMATION = "no_information"
    OUT_OF_SCOPE = "out_of_scope"


class GuardrailsConfig(BaseModel):
    max_sentences: int = Field(default=MAX_SENTENCES)
    max_chars_per_sentence: int = Field(default=MAX_CHARS_PER_SENTENCE)
    educational_links: Dict[str, str] = Field(default_factory=lambda: _load_educational_links())


def _load_educational_links() -> dict[str, str]:
    """Load AMFI/SEBI educational links from phase0/refusal_taxonomy.json."""
    links = dict(EDUCATIONAL_LINKS)
    if not REFUSAL_TAXONOMY_PATH.is_file():
        return links
    try:
        data = json.loads(REFUSAL_TAXONOMY_PATH.read_text(encoding="utf-8"))
        allowlist = data.get("educational_links_allowlist", [])
        url_by_id = {item["id"]: item["url"] for item in allowlist if "url" in item}
        if "amfi_investor_corner" in url_by_id:
            links["advisory"] = url_by_id["amfi_investor_corner"]
        if "sebi_investor_home" in url_by_id:
            links["comparison"] = url_by_id["sebi_investor_home"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return links


class ResponseGuardrails:
    """Ensures response compliance with safety and privacy requirements."""

    def __init__(self, config: Optional[GuardrailsConfig] = None):
        self.config = config or GuardrailsConfig()

        self.forbidden_patterns = [
            r"\b(recommend|suggest|advise)\b.+\b(you|to)\b.+\b(invest|buy)\b",
            r"\b(you|I)\s+(should|must|have to)\s+(invest|buy|purchase)\b",
            r"\b(best|better|good|bad)\s+(investment|choice|option)\b",
            r"\b(guaranteed|assured|certain)\s+(returns|profit|gain)\b",
            r"\b(your|you)\s+(money|capital|funds)\s+(will|would)\s+(grow|increase)\b",
            r"\b(performance|returns)\s+(will|would)\s+(be|be better|be higher)\b",
            r"\b(buy|purchase)\s+(this|that|these|those)\s+(fund|scheme)\b",
            r"\binvest\s+in\s+(this|that|these|those)\s+(fund|scheme)\b",
        ]

        self.personal_url_patterns = [
            r".*(login|signin|sign-in|auth|authenticate).*",
            r".*(account|portfolio|dashboard|profile).*",
            r".*(personal|individual|customer|client).*",
            r".*(pan|aadhaar|kyc|verification).*",
            r".*(my|your|our).+(holdings|investments|transactions).*",
        ]

    def _split_sentences(self, response: str) -> list[str]:
        if re.search(r"\b(NAV|AUM|expense ratio)\b", response, re.IGNORECASE):
            parts = re.split(r"\.\s+(?=[A-Z])", response)
            return [p.strip().rstrip(".") for p in parts if p.strip()]
        return [s.strip() for s in re.split(r"[.!?]+", response) if s.strip()]

    def validate_response_content(self, response: str) -> Tuple[bool, List[str]]:
        issues: List[str] = []

        for pattern in self.forbidden_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append(f"Contains advisory language: {pattern}")

        sentences = self._split_sentences(response)
        for i, sentence in enumerate(sentences):
            if len(sentence) > self.config.max_chars_per_sentence:
                issues.append(f"Sentence {i + 1} too long: {len(sentence)} chars")

        if len(sentences) > self.config.max_sentences:
            issues.append(f"Too many sentences: {len(sentences)} > {self.config.max_sentences}")

        return len(issues) == 0, issues

    def _coerce_response_type(self, response_type: ResponseType | str) -> ResponseType:
        if isinstance(response_type, ResponseType):
            return response_type
        return ResponseType(response_type)

    def validate_citation_url(
        self,
        url: str,
        response_type: ResponseType | str,
    ) -> Tuple[bool, str]:
        rt = self._coerce_response_type(response_type)

        if rt in (
            ResponseType.ANSWER_NO_CITATION,
            ResponseType.NO_INFORMATION,
            ResponseType.OUT_OF_SCOPE,
            ResponseType.REFUSAL_PERSONAL_INFO,
        ):
            if url:
                return False, f"No citation allowed for {rt.value}"
            return True, "No citation required"

        if rt in (ResponseType.REFUSAL_ADVISORY, ResponseType.REFUSAL_COMPARISON):
            return True, "Refusal path uses educational link, not corpus citation"

        if not url:
            return False, "Citation URL is required for grounded factual answers"

        url_lower = url.lower()
        for allowed in ALLOWED_CITATION_URLS:
            if allowed.lower() in url_lower or url_lower in allowed.lower():
                return True, "Valid citation URL"

        for pattern in self.personal_url_patterns:
            if re.search(pattern, url_lower):
                return False, "URL contains personal information patterns"

        return False, f"URL not from allowed corpus: {url}"

    def generate_refusal_response(self, refusal_type: str) -> Dict[str, str]:
        templates = {
            "advisory": {
                "response": (
                    "I can only provide factual information about mutual funds and cannot "
                    "give investment advice. For investment guidance, please consult a "
                    "qualified financial advisor."
                ),
                "citation": "",
                "footer": "",
                "educational_link": self.config.educational_links["advisory"],
                "response_type": ResponseType.REFUSAL_ADVISORY.value,
            },
            "comparison": {
                "response": (
                    "I can provide individual fund information but cannot make comparisons "
                    "or recommendations between different mutual funds."
                ),
                "citation": "",
                "footer": "",
                "educational_link": self.config.educational_links["comparison"],
                "response_type": ResponseType.REFUSAL_COMPARISON.value,
            },
            "personal_info": {
                "response": (
                    "I cannot access personal accounts or provide individual portfolio "
                    "information. For account-specific queries, please contact your "
                    "mutual fund company or advisor directly."
                ),
                "citation": "",
                "footer": "",
                "educational_link": "",
                "response_type": ResponseType.REFUSAL_PERSONAL_INFO.value,
            },
            "no_information": {
                "response": NO_ANSWER_MESSAGE,
                "citation": "",
                "footer": "",
                "educational_link": "",
                "response_type": ResponseType.NO_INFORMATION.value,
            },
            "out_of_scope": {
                "response": OUT_OF_SCOPE_MESSAGE,
                "citation": "",
                "footer": "",
                "educational_link": "",
                "response_type": ResponseType.OUT_OF_SCOPE.value,
            },
        }
        return dict(templates.get(refusal_type, templates["no_information"]))

    def format_answer_response(
        self,
        answer: str,
        citation_url: str,
        last_updated: str,
    ) -> Dict[str, str]:
        is_valid, issues = self.validate_response_content(answer)
        if not is_valid:
            raise ValueError(f"Invalid answer content: {', '.join(issues)}")

        is_valid_citation, citation_message = self.validate_citation_url(
            citation_url,
            ResponseType.ANSWER_WITH_CITATION,
        )
        if not is_valid_citation:
            raise ValueError(f"Invalid citation: {citation_message}")

        return {
            "response": answer,
            "citation": citation_url,
            "footer": f"Last updated from sources: {last_updated}",
            "educational_link": "",
            "response_type": ResponseType.ANSWER_WITH_CITATION.value,
        }

    def check_privacy_compliance(self, response: Dict[str, str]) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        response_type = response.get("response_type", "")

        citation = response.get("citation", "")
        if citation:
            is_valid, message = self.validate_citation_url(citation, response_type)
            if not is_valid:
                issues.append(f"Invalid citation URL: {message}")

        edu_link = response.get("educational_link", "")
        if edu_link and response_type in (
            ResponseType.NO_INFORMATION.value,
            ResponseType.OUT_OF_SCOPE.value,
            ResponseType.REFUSAL_PERSONAL_INFO.value,
        ):
            issues.append("Educational link not allowed for no-information or personal-info responses")

        if edu_link:
            for pattern in self.personal_url_patterns:
                if re.search(pattern, edu_link.lower()):
                    issues.append(f"Educational link contains personal patterns: {pattern}")

        return len(issues) == 0, issues

    def generate_final_response(
        self,
        query: str,
        intent: str,
        retrieved_chunks: Optional[List[Dict]] = None,
        answer: Optional[str] = None,
        citation_url: Optional[str] = None,
        last_updated: Optional[str] = None,
        has_grounded_answer: bool = False,
    ) -> Dict[str, str]:
        del query  # reserved for logging / future use

        if intent == "personal_info":
            return self.generate_refusal_response("personal_info")

        if intent in ("advisory", "comparison"):
            return self.generate_refusal_response(intent)

        if not has_grounded_answer or not citation_url or not last_updated:
            return self.generate_refusal_response("no_information")

        try:
            return self.format_answer_response(
                answer=answer or NO_ANSWER_MESSAGE,
                citation_url=citation_url,
                last_updated=last_updated,
            )
        except ValueError:
            return self.generate_refusal_response("no_information")


def main() -> int:
    guardrails = ResponseGuardrails()

    test_cases = [
        ("Grounded answer", "factual", True, "Choice offers index funds.", ALLOWED_CITATION_URLS[0], "2026-05-03"),
        ("No information", "factual", False, None, None, None),
        ("Personal info", "personal_info", False, None, None, None),
        ("Advisory", "advisory", False, None, None, None),
    ]

    print("Guardrails Test Results:")
    print("=" * 60)
    for name, intent, grounded, answer, citation, updated in test_cases:
        result = guardrails.generate_final_response(
            query="test",
            intent=intent,
            has_grounded_answer=grounded,
            answer=answer,
            citation_url=citation,
            last_updated=updated,
        )
        print(f"\n{name}: {result['response_type']}")
        print(f"  Citation: {result['citation'] or '(none)'}")
        print(f"  Educational: {result['educational_link'] or '(none)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
