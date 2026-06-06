#!/usr/bin/env python3
"""
Phase 3 — Complete generation pipeline runner.

1. Intent classification and query routing
2. Retrieval from Phase 2 indexes (if applicable)
3. Answer generation with guardrails
4. Citation only when grounded; no URLs on unknown/personal-info paths
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase2.rag.config import DEFAULT_TOP_K

from .answer_generator import AnswerGenerator
from .config import GROQ_MODEL
from .guardrails import ResponseGuardrails, ResponseType
from .query_service import QueryService, load_phase2_retriever


def run_phase3_pipeline(
    queries: List[str],
    phase2_dir: Optional[Path] = None,
    use_llm: bool = False,
    output_file: Optional[Path] = None,
    top_k: int = DEFAULT_TOP_K,
    groq_model: str = GROQ_MODEL,
) -> Dict[str, Any]:
    print("=" * 60)
    print("Phase 3 — Generation Pipeline")
    print("=" * 60)

    generator = AnswerGenerator(model_name=groq_model, use_llm=use_llm)
    service = QueryService(
        phase2_dir=phase2_dir,
        use_llm=use_llm,
        top_k=top_k,
        groq_model=groq_model,
    )
    service.initialize()
    retriever = service._retriever
    if retriever is not None:
        print(f"Loaded Phase 2 retriever from {phase2_dir / 'retrieval'}")
    elif service.load_error:
        print(f"Failed to load Phase 2 retriever: {service.load_error}")

    results: List[Dict[str, Any]] = []
    stats = {
        "total_queries": len(queries),
        "intent_distribution": {},
        "response_types": {},
        "citations_provided": 0,
        "refusals_generated": 0,
        "no_info_responses": 0,
        "no_url_responses": 0,
        "average_confidence": 0.0,
        "processing_time": 0.0,
    }

    start_time = time.time()

    for i, query in enumerate(queries):
        print(f"\nProcessing Query {i + 1}/{len(queries)}: {query}")
        print("-" * 40)

        retrieved_chunks: List[Dict[str, Any]] = []
        if retriever:
            try:
                retrieved_chunks = retriever.hybrid_search(query, top_k=top_k)
                print(f"Retrieved {len(retrieved_chunks)} chunks")
            except Exception as exc:
                print(f"Retrieval failed: {exc}")

        response = generator.generate_response(query, retrieved_chunks, use_llm)
        results.append(response)

        intent = response["intent"]
        stats["intent_distribution"][intent] = stats["intent_distribution"].get(intent, 0) + 1

        response_type = response["response_type"]
        stats["response_types"][response_type] = stats["response_types"].get(response_type, 0) + 1

        if response["has_citation"]:
            stats["citations_provided"] += 1

        if "refusal" in response_type:
            stats["refusals_generated"] += 1

        if response_type == ResponseType.NO_INFORMATION.value:
            stats["no_info_responses"] += 1

        if not response.get("citation") and not response.get("educational_link"):
            stats["no_url_responses"] += 1

        stats["average_confidence"] += response["confidence"]

        print(f"Intent: {intent} (confidence: {response['confidence']:.3f})")
        print(f"Response Type: {response_type}")
        print(f"Grounded: {response.get('has_grounded_answer', False)}")
        print(f"Response: {response['response']}")
        print(f"Citation: {response['citation'] or '(none)'}")
        print(f"Footer: {response['footer'] or '(none)'}")
        print(f"Educational: {response['educational_link'] or '(none)'}")

    stats["processing_time"] = time.time() - start_time
    if queries:
        stats["average_confidence"] /= len(queries)

    report = {
        "pipeline_version": "3.1",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "configuration": {
            "use_llm": use_llm,
            "llm_provider": "groq",
            "groq_model": groq_model,
            "phase2_available": retriever is not None,
            "phase2_directory": str(phase2_dir) if phase2_dir else None,
            "top_k": top_k,
        },
        "statistics": stats,
        "results": results,
    }

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nPipeline results saved to: {output_file}")

    return report


def test_guardrails_compliance(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    guardrails = ResponseGuardrails()
    report = {
        "total_responses": len(results),
        "compliant_responses": 0,
        "privacy_violations": 0,
        "content_violations": 0,
        "citation_violations": 0,
        "violations": [],
    }

    for i, result in enumerate(results):
        is_privacy_compliant, privacy_issues = guardrails.check_privacy_compliance(result)
        is_content_compliant, content_issues = guardrails.validate_response_content(
            result["response"]
        )

        citation_issues: List[str] = []
        response_type = result.get("response_type", "")
        citation = result.get("citation", "")

        if response_type == ResponseType.NO_INFORMATION.value:
            if citation or result.get("educational_link") or result.get("footer"):
                citation_issues.append("No-information response must have no URLs or footer")
        elif response_type == ResponseType.REFUSAL_PERSONAL_INFO.value:
            if citation or result.get("educational_link"):
                citation_issues.append("Personal-info refusal must have no URLs")
        elif result.get("has_citation"):
            is_citation_valid, citation_message = guardrails.validate_citation_url(
                citation,
                ResponseType.ANSWER_WITH_CITATION,
            )
            if not is_citation_valid:
                citation_issues.append(citation_message)

        is_compliant = (
            is_privacy_compliant
            and is_content_compliant
            and len(citation_issues) == 0
        )

        if is_compliant:
            report["compliant_responses"] += 1
        else:
            report["violations"].append({
                "query_index": i,
                "response_type": response_type,
                "privacy_issues": privacy_issues,
                "content_issues": content_issues,
                "citation_issues": citation_issues,
            })
            if privacy_issues:
                report["privacy_violations"] += 1
            if content_issues:
                report["content_violations"] += 1
            if citation_issues:
                report["citation_violations"] += 1

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 - Generation pipeline")
    parser.add_argument("--queries", type=str, nargs="+", help="Queries to process")
    parser.add_argument("--queries-file", type=Path, help="File with one query per line")
    parser.add_argument(
        "--phase2-dir",
        type=Path,
        default=Path("data/phase2_results"),
        help="Phase 2 output directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/phase3_results/phase3_pipeline_report.json"),
        help="Output report path",
    )
    parser.add_argument("--use-llm", action="store_true", help="Enable Groq LLM generation")
    parser.add_argument("--groq-model", type=str, default=GROQ_MODEL, help="Groq model name")
    parser.add_argument("--test-compliance", action="store_true", help="Run guardrails compliance check")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args()

    queries: List[str] = []
    if args.queries:
        queries = args.queries
    elif args.queries_file and args.queries_file.exists():
        queries = [
            line.strip()
            for line in args.queries_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        queries = [
            "What is the NAV of Choice Mutual Fund?",
            "Which fund should I invest in for retirement?",
            "Compare ICICI Prudential vs Union Mutual Fund performance",
            "Check my account balance and holdings",
            "Tell me about SIP investments in LIC Mutual Fund",
            "What are the tax benefits of ELSS funds?",
            "How does expense ratio affect mutual fund returns?",
            "Is it good to invest in debt funds now?",
            "What is the AUM of Unifi Mutual Fund?",
            "What is the weather in Mumbai today?",
        ]
        print("Using default test queries")

    if not queries:
        print("No queries provided", file=sys.stderr)
        return 1

    print(f"Processing {len(queries)} queries")

    try:
        report = run_phase3_pipeline(
            queries=queries,
            phase2_dir=args.phase2_dir,
            use_llm=args.use_llm,
            output_file=args.output,
            top_k=args.top_k,
            groq_model=args.groq_model,
        )

        stats = report["statistics"]
        print("\n" + "=" * 60)
        print("Phase 3 Pipeline Summary")
        print("=" * 60)
        print(f"Total Queries: {stats['total_queries']}")
        print(f"Processing Time: {stats['processing_time']:.2f} seconds")
        print(f"Average Confidence: {stats['average_confidence']:.3f}")
        print(f"Citations Provided: {stats['citations_provided']}")
        print(f"Refusals Generated: {stats['refusals_generated']}")
        print(f"No-Info Responses: {stats['no_info_responses']}")
        print(f"No-URL Responses: {stats['no_url_responses']}")

        print("\nIntent Distribution:")
        for intent, count in stats["intent_distribution"].items():
            print(f"  {intent}: {count}")

        print("\nResponse Types:")
        for response_type, count in stats["response_types"].items():
            print(f"  {response_type}: {count}")

        if args.test_compliance:
            print("\n" + "=" * 60)
            print("Guardrails Compliance Test")
            print("=" * 60)
            compliance = test_guardrails_compliance(report["results"])
            print(
                f"Compliant Responses: "
                f"{compliance['compliant_responses']}/{compliance['total_responses']}"
            )
            print(f"Privacy Violations: {compliance['privacy_violations']}")
            print(f"Content Violations: {compliance['content_violations']}")
            print(f"Citation Violations: {compliance['citation_violations']}")
            if compliance["violations"]:
                for v in compliance["violations"]:
                    print(f"  Query {v['query_index']}: {v['response_type']}")
                    for key in ("privacy_issues", "content_issues", "citation_issues"):
                        if v[key]:
                            print(f"    {key}: {', '.join(v[key])}")

        print("\nPhase 3 pipeline completed successfully.")
        return 0

    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
