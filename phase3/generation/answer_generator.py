#!/usr/bin/env python3
"""
Phase 3 — Answer generation with guardrails.

Generates factual answers using retrieved chunks:
- Facts-only, max three sentences
- Citation only when evidence gate passes
- No URLs when answer is unknown or query is personal-info
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    DEFAULT_TOP_K,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    MAX_CHARS_PER_SENTENCE,
    MAX_SENTENCES,
    MIN_QUERY_TERM_OVERLAP,
    MIN_RETRIEVAL_SCORE,
    NO_ANSWER_MESSAGE,
    STOP_WORDS,
)
from .fact_extractor import (
    build_answer_from_chunks,
    chunk_supports_query,
    detect_query_metric,
    extract_fund_names_from_query,
    is_out_of_domain_query,
)
from phase2.rag.fund_records import (
    UNSUPPORTED_CORPUS_METRICS,
    is_query_in_corpus_scope,
    requires_named_scheme,
)
from .guardrails import ResponseGuardrails, ResponseType
from .intent_classifier import IntentClassifier, QueryIntent


def _query_terms(query: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def _term_overlap(query: str, text: str) -> float:
    q_terms = _query_terms(query)
    if not q_terms:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for term in q_terms if term in text_lower)
    return matches / len(q_terms)


_NO_INFO_PATTERNS = (
    "don't have that information",
    "don't have information",
    "do not have information",
    "not in the context",
    "not in the provided context",
    "not mentioned in",
    "does not mention",
    "do not mention",
    "no information about",
    "cannot find",
    "unable to find",
    "i don't know",
)


def _is_no_info_answer(text: str) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in _NO_INFO_PATTERNS)


def _is_grounded_factual_answer(
    answer: str,
    query: str,
    metric: str | None,
) -> bool:
    """Reject chunk headers or answers that omit the requested fact."""
    if not answer or _is_no_info_answer(answer):
        return False

    if metric in UNSUPPORTED_CORPUS_METRICS:
        return False

    stripped = answer.strip()
    if re.fullmatch(r"[A-Z0-9][^.]+\([^)]+\)\.", stripped) and not re.search(r"\d", stripped):
        return False

    numeric_metrics = {
        "nav", "aum", "expense_ratio", "sip", "minimum_investment", "returns",
    }
    text_metrics = {"risk", "rating", "fund_manager", "category", "exit_load"}
    if metric in numeric_metrics and not re.search(r"\d", stripped):
        return False
    if metric in text_metrics and len(stripped) < 20:
        return False

    if metric is None and not re.search(r"\d", stripped):
        if re.search(r"\([^)]*mutual fund[^)]*\)\.?\s*$", stripped, re.IGNORECASE):
            return False
        if len(stripped) < 80:
            return False

    return True


def _sanitize_answer(text: str) -> str:
    """Strip URLs, normalize whitespace, enforce max sentence count and length."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()

    if re.search(r"\b(NAV|AUM|expense ratio|Exit Load|SIP)\b", text, re.IGNORECASE):
        if len(text) > MAX_CHARS_PER_SENTENCE * MAX_SENTENCES:
            text = text[: MAX_CHARS_PER_SENTENCE * MAX_SENTENCES].rsplit(" ", 1)[0] + "."
        return text if text.endswith(".") else text + "."

    raw_parts = re.split(r"(?<=[.!?])\s+", text)
    sentences: list[str] = []
    for part in raw_parts:
        part = part.strip().rstrip(".")
        if not part:
            continue
        part += "."
        if len(part) > MAX_CHARS_PER_SENTENCE:
            part = part[: MAX_CHARS_PER_SENTENCE - 1].rstrip() + "."
        sentences.append(part)
        if len(sentences) >= MAX_SENTENCES:
            break

    return " ".join(sentences) if sentences else NO_ANSWER_MESSAGE


class AnswerGenerator:
    """Generates factual answers using retrieved chunks."""

    def __init__(
        self,
        model_name: str = GROQ_MODEL,
        temperature: float = GROQ_TEMPERATURE,
        max_tokens: int = GROQ_MAX_TOKENS,
        use_llm: bool = False,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_llm = use_llm

        self.intent_classifier = IntentClassifier()
        self.guardrails = ResponseGuardrails()

        self.system_prompt = """You are a factual mutual fund information assistant.

Rules:
1. Answer using ONLY the information from the provided context
2. Maximum 3 sentences
3. No investment advice, recommendations, or comparisons
4. No personal information or account access
5. If information is not in the context, say you don't have that information
6. Do not include any URLs or citations in your answer

Context: {context}"""

    def is_query_out_of_scope(self, query: str) -> bool:
        """True when the query should not retrieve or answer from the five-AMC corpus."""
        if is_out_of_domain_query(query):
            return True
        fund_names = extract_fund_names_from_query(query)
        if not is_query_in_corpus_scope(query, fund_names=fund_names):
            return True
        metric = detect_query_metric(query)
        if requires_named_scheme(query, metric, fund_names):
            return True
        if metric in UNSUPPORTED_CORPUS_METRICS:
            return True
        return False

    def _out_of_scope_response(
        self,
        intent: str,
        confidence: float,
        *,
        chunks_used: int = 0,
    ) -> Dict[str, Any]:
        response = self.guardrails.generate_refusal_response("out_of_scope")
        response.update({
            "intent": intent,
            "confidence": confidence,
            "chunks_used": chunks_used,
            "has_citation": False,
            "has_grounded_answer": False,
            "generation_time": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
        return response

    def has_sufficient_evidence(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if not chunks or is_out_of_domain_query(query):
            return False, None

        metric = detect_query_metric(query)
        fund_names = extract_fund_names_from_query(query)

        ranked = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)
        for candidate in ranked:
            score = candidate.get("score", 0)
            if score < MIN_RETRIEVAL_SCORE:
                continue

            text = candidate.get("text", "")
            overlap = _term_overlap(query, text)
            if overlap < MIN_QUERY_TERM_OVERLAP:
                continue

            q_terms = _query_terms(query)
            if q_terms and not any(term in text.lower() for term in q_terms):
                continue

            if metric and not chunk_supports_query(
                candidate, query, metric=metric, fund_names=fund_names
            ):
                continue

            return True, candidate

        return False, None

    def extract_relevant_info(
        self,
        chunk: Dict[str, Any],
        query: str,
    ) -> str:
        chunk_text = chunk.get("text", "")
        query_lower = query.lower()
        chunk_lower = chunk_text.lower()

        financial_terms = [
            "nav", "expense ratio", "exit load", "sip", "returns", "fund",
            "scheme", "aum", "benchmark", "lock-in", "minimum",
        ]
        query_terms = _query_terms(query)
        relevant_terms = [
            t for t in financial_terms
            if t in query_lower or t in chunk_lower
        ] + list(query_terms)

        sentences = re.split(r"(?<=[.!?])\s+", chunk_text)
        relevant_sentences = []
        for sentence in sentences:
            sl = sentence.lower()
            if any(term in sl for term in relevant_terms):
                relevant_sentences.append(sentence.strip())

        if relevant_sentences:
            return " ".join(relevant_sentences[:2])
        return chunk_text[:400].strip()

    def generate_answer_with_llm(self, query: str, context: str) -> str:
        if not self.use_llm or not context.strip():
            return self._simple_extraction(query, context)

        try:
            return self._call_groq_api(query, context)
        except Exception:
            return self._simple_extraction(query, context)

    def _call_groq_api(self, query: str, context: str) -> str:
        from groq import Groq

        client = Groq(timeout=25.0, max_retries=1)
        prompt = self.system_prompt.format(context=context)

        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _simple_extraction(self, query: str, context: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", context)
        query_terms = _query_terms(query)

        best_sentence = ""
        best_score = 0.0
        for sentence in sentences:
            sl = sentence.lower().strip()
            if len(sl) < 20:
                continue
            score = sum(1 for t in query_terms if t in sl)
            if score > best_score:
                best_score = score
                best_sentence = sentence.strip()

        if best_sentence:
            return _sanitize_answer(best_sentence)

        if sentences and len(sentences[0].strip()) > 20:
            return _sanitize_answer(sentences[0].strip())

        return NO_ANSWER_MESSAGE

    def get_last_updated_date(self, chunks: List[Dict[str, Any]]) -> str:
        dates: List[str] = []
        for chunk in chunks:
            ingested_at = chunk.get("metadata", {}).get("ingested_at", "")
            if ingested_at:
                dates.append(ingested_at.split("T")[0])
        return max(dates) if dates else "2026-05-03"

    def generate_response(
        self,
        query: str,
        retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
        use_llm: Optional[bool] = None,
    ) -> Dict[str, Any]:
        use_llm = self.use_llm if use_llm is None else use_llm
        intent, confidence = self.intent_classifier.classify_query(query)

        if intent in (QueryIntent.ADVISORY, QueryIntent.COMPARISON, QueryIntent.PERSONAL_INFO):
            response = self.guardrails.generate_final_response(
                query=query,
                intent=intent.value,
            )
            response.update({
                "intent": intent.value,
                "confidence": confidence,
                "chunks_used": 0,
                "has_citation": False,
                "has_grounded_answer": False,
                "generation_time": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            })
            return response

        if is_out_of_domain_query(query):
            return self._out_of_scope_response(intent.value, confidence)

        fund_names = extract_fund_names_from_query(query)
        metric = detect_query_metric(query)
        if not is_query_in_corpus_scope(query, fund_names=fund_names):
            return self._out_of_scope_response(intent.value, confidence)

        if requires_named_scheme(query, metric, fund_names):
            return self._out_of_scope_response(intent.value, confidence)

        if metric in UNSUPPORTED_CORPUS_METRICS:
            return self._out_of_scope_response(intent.value, confidence)

        has_evidence, best_chunk = self.has_sufficient_evidence(
            retrieved_chunks or [],
            query,
        )

        citation_url = None
        last_updated = None
        answer = None

        if has_evidence and best_chunk:
            structured_answer, source_chunk = build_answer_from_chunks(
                retrieved_chunks or [],
                query,
            )
            used_structured = bool(structured_answer and source_chunk)

            if used_structured:
                answer = _sanitize_answer(structured_answer)
                best_chunk = source_chunk
            elif metric:
                has_evidence = False
                answer = None
            else:
                context = self.extract_relevant_info(best_chunk, query)
                if use_llm:
                    raw_answer = self.generate_answer_with_llm(query, context)
                else:
                    raw_answer = self._simple_extraction(query, context)
                answer = _sanitize_answer(raw_answer)

            if _is_no_info_answer(answer) or answer == NO_ANSWER_MESSAGE:
                has_evidence = False
                answer = None
            elif not _is_grounded_factual_answer(answer, query, metric):
                has_evidence = False
                answer = None
            elif (
                not used_structured
                and detect_query_metric(query)
                and not chunk_supports_query(best_chunk, query)
            ):
                has_evidence = False
                answer = None

            if has_evidence and answer:
                citation_url = best_chunk.get("source_url", "")
                last_updated = self.get_last_updated_date([best_chunk])

        response = self.guardrails.generate_final_response(
            query=query,
            intent=intent.value,
            retrieved_chunks=retrieved_chunks,
            answer=answer,
            citation_url=citation_url,
            last_updated=last_updated,
            has_grounded_answer=has_evidence,
        )

        response.update({
            "intent": intent.value,
            "confidence": confidence,
            "chunks_used": len(retrieved_chunks) if retrieved_chunks else 0,
            "has_citation": bool(response.get("citation")),
            "has_grounded_answer": (
                response.get("response_type") == ResponseType.ANSWER_WITH_CITATION.value
            ),
            "generation_time": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
        return response

    def batch_generate_responses(
        self,
        queries: List[str],
        retriever: Any = None,
        use_llm: Optional[bool] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        responses = []
        for query in queries:
            chunks = retriever.hybrid_search(query, top_k=top_k) if retriever else []
            responses.append(self.generate_response(query, chunks, use_llm))
        return responses


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Phase 3 - Answer generator test")
    parser.add_argument("--query", type=str, help="Single query to test")
    parser.add_argument("--retrieval-index", type=Path, help="Retrieval index directory")
    parser.add_argument("--use-llm", action="store_true", help="Enable Groq LLM generation")
    parser.add_argument("--model", type=str, default=GROQ_MODEL, help="Groq model name")
    args = parser.parse_args()

    generator = AnswerGenerator(model_name=args.model, use_llm=args.use_llm)

    retriever = None
    if args.retrieval_index and args.retrieval_index.exists():
        from phase2.rag.retrieval import HybridRetriever
        retriever = HybridRetriever.load_index(args.retrieval_index)

    queries = [args.query] if args.query else [
        "What is the NAV of Choice Mutual Fund?",
        "Which fund should I invest in?",
        "Check my account balance",
    ]

    for query in queries:
        chunks = retriever.hybrid_search(query, top_k=3) if retriever else []
        response = generator.generate_response(query, chunks)
        print(f"\nQuery: {query}")
        print(f"Type: {response['response_type']}")
        print(f"Response: {response['response']}")
        print(f"Citation: {response['citation'] or '(none)'}")
        print(f"Educational: {response['educational_link'] or '(none)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
