#!/usr/bin/env python3
"""
Phase 3 — Intent classification for query routing.

Classifies user queries into categories for appropriate handling:
- Factual FAQ: Information-seeking questions about mutual funds
- Advisory: Investment advice, recommendations, "what should I buy"
- Comparison: Fund comparisons, performance comparisons
- Personal Information: Account access, personal data requests
- No Information: Queries outside corpus scope
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class QueryIntent(Enum):
    """Query intent categories."""
    FACTUAL = "factual"
    ADVISORY = "advisory"
    COMPARISON = "comparison"
    PERSONAL_INFO = "personal_info"
    NO_INFO = "no_info"


class IntentClassifier:
    """Classifies user queries based on intent and content."""
    
    def __init__(self):
        """Initialize intent classifier with keyword patterns."""
        
        # Advisory patterns - seeking advice or recommendations
        self.advisory_patterns = [
            r"(should|would|could|recommend|suggest|advise).+(buy|invest|choose|pick)",
            r"which\s+(fund|scheme|investment).+(should|invest|buy|choose)",
            r"what\s+(fund|scheme|investment).+(should|would|recommend)",
            r"which\s+(fund|scheme|investment).+(best|good|better|choose)",
            r"is\s+it\s+(good|bad|wise|safe)\s+(to|for)\s+(invest|buy)",
            r"how\s+much\s+(should|would|could)\s+(invest|allocate)",
            r"(investment|portfolio)\s+(advice|recommendation|guidance)",
            r"(tell|give)\s+me\s+(advice|recommendation|suggestion)",
            r"what\s+do\s+you\s+(think|believe|recommend)",
            r"(is|are)\s+(this|that|it)\s+(good|bad|safe|risky)",
            r"good\s+to\s+invest",
        ]
        
        # Comparison patterns - comparing funds or performance
        self.comparison_patterns = [
            r"\b(compare|comparison|vs|versus)\b",
            r"\b(better|worse|best|worst)\b.+(than|compared)",
            r"(which|what)\s+(is|are)\s+(better|best|worse)",
            r"\b(difference|differences)\b.+(between|among)",
            r"\bperformance\b",
            r"\b(top|best|worst)\s+(performing|funds|schemes)\b",
        ]
        
        # Personal information patterns - account access, personal data
        self.personal_info_patterns = [
            r"\b(my|our)\s+(account|portfolio|holdings|investments|balance|transactions)\b",
            r"\b(account|portfolio)\s+(balance|holdings|details|statement)\b",
            r"\b(login|sign\s*in|sign-in|dashboard|profile)\b",
            r"\b(pan|aadhaar|kyc|otp|password)\b",
            r"\b(check|view|see)\s+(my|our)\s+(account|portfolio|holdings)\b",
            r"\bpersonal\s+(advice|recommendation|information)\b",
        ]
        
        # Financial factual patterns - legitimate information seeking
        self.factual_keywords = [
            "what is", "what are", "how does", "explain", "tell me about",
            "information about", "details of", "features of", "benefits of",
            "NAV", "expense ratio", "exit load", "SIP", "lump sum",
            "fund manager", "AUM", "risk", "portfolio", "scheme",
            "returns", "performance", "benchmark", "category", "rating"
        ]
        
        # Mutual fund entities for context
        self.amc_names = [
            "choice", "icici prudential", "icici", "union", "lic", "unifi"
        ]
        
        self.fund_types = [
            "index fund", "elss", "tax saving", "debt", "equity", "hybrid",
            "large cap", "mid cap", "small cap", "flexi cap", "multi cap"
        ]
    
    def classify_query(self, query: str) -> Tuple[QueryIntent, float]:
        """Classify query intent with confidence score."""
        query_lower = query.lower().strip()
        
        # Personal information requests (highest priority)
        personal_score = self._calculate_pattern_score(query_lower, self.personal_info_patterns)
        if personal_score > 0.0:
            return QueryIntent.PERSONAL_INFO, personal_score

        # Advisory before comparison — "which fund should I buy" is advice, not comparison
        advisory_score = self._calculate_pattern_score(query_lower, self.advisory_patterns)
        if advisory_score > 0.0:
            return QueryIntent.ADVISORY, advisory_score

        comparison_score = self._calculate_pattern_score(query_lower, self.comparison_patterns)
        if comparison_score > 0.0:
            return QueryIntent.COMPARISON, comparison_score
        
        # Check for factual queries
        factual_score = self._calculate_factual_score(query_lower)
        if factual_score > 0.2:
            return QueryIntent.FACTUAL, factual_score
        
        # Default to no information
        return QueryIntent.NO_INFO, 0.1
    
    def _calculate_pattern_score(self, query: str, patterns: List[str]) -> float:
        """Return confidence based on pattern hits (any hit is significant)."""
        matches = sum(1 for pattern in patterns if re.search(pattern, query, re.IGNORECASE))
        if matches == 0:
            return 0.0
        return min(0.5 + matches * 0.15, 1.0)
    
    def _calculate_factual_score(self, query: str) -> float:
        """Calculate factual query score based on keywords."""
        score = 0.0
        
        # Check for factual question patterns
        if any(keyword in query for keyword in ["what is", "what are", "how does", "explain", "tell me about"]):
            score += 0.3
        
        # Check for financial keywords
        financial_matches = sum(1 for keyword in self.factual_keywords if keyword in query)
        score += min(financial_matches * 0.1, 0.5)
        
        # Check for AMC names
        amc_matches = sum(1 for amc in self.amc_names if amc in query)
        score += min(amc_matches * 0.1, 0.2)
        
        # Check for fund types
        fund_matches = sum(1 for fund_type in self.fund_types if fund_type in query)
        score += min(fund_matches * 0.1, 0.2)
        
        return min(score, 1.0)
    
    def get_retrieval_context(self, query: str, intent: QueryIntent) -> Dict[str, any]:
        """Get retrieval context based on intent."""
        context = {
            "query": query,
            "intent": intent.value,
            "should_retrieve": False,
            "max_chunks": 0,
            "min_score_threshold": 0.0
        }
        
        if intent == QueryIntent.FACTUAL:
            context.update({
                "should_retrieve": True,
                "max_chunks": 5,
                "min_score_threshold": 0.3
            })
        elif intent == QueryIntent.ADVISORY:
            context.update({
                "should_retrieve": False,
                "reason": "Advisory queries should be refused"
            })
        elif intent == QueryIntent.COMPARISON:
            context.update({
                "should_retrieve": False,
                "reason": "Comparison queries should be refused"
            })
        elif intent == QueryIntent.PERSONAL_INFO:
            context.update({
                "should_retrieve": False,
                "reason": "Personal information requests should be refused"
            })
        else:  # NO_INFO
            context.update({
                "should_retrieve": True,
                "max_chunks": 3,
                "min_score_threshold": 0.5  # Higher threshold for no-info queries
            })
        
        return context
    
    def explain_classification(self, query: str) -> Dict[str, any]:
        """Explain the classification decision."""
        intent, confidence = self.classify_query(query)
        context = self.get_retrieval_context(query, intent)
        
        explanation = {
            "query": query,
            "intent": intent.value,
            "confidence": confidence,
            "should_retrieve": context["should_retrieve"],
            "reasoning": self._get_reasoning(query, intent),
            "retrieval_params": {
                "max_chunks": context["max_chunks"],
                "min_score_threshold": context["min_score_threshold"]
            }
        }
        
        if not context["should_retrieve"]:
            explanation["refusal_reason"] = context.get("reason", "Query not suitable for retrieval")
        
        return explanation
    
    def _get_reasoning(self, query: str, intent: QueryIntent) -> str:
        """Get reasoning for classification."""
        if intent == QueryIntent.FACTUAL:
            return "Query contains factual keywords and patterns suitable for information retrieval"
        elif intent == QueryIntent.ADVISORY:
            return "Query seeks investment advice or recommendations, which should be refused"
        elif intent == QueryIntent.COMPARISON:
            return "Query requests comparison between funds, which should be refused"
        elif intent == QueryIntent.PERSONAL_INFO:
            return "Query requests personal information or account access, which should be refused"
        else:  # NO_INFO
            return "Query doesn't match known patterns, may be outside corpus scope"


def main() -> int:
    """Test intent classifier."""
    import json
    
    test_queries = [
        "What is the NAV of Choice Mutual Fund?",
        "Which fund should I invest in for retirement?",
        "Compare ICICI Prudential vs Union Mutual Fund performance",
        "Check my account balance",
        "Tell me about SIP investments",
        "How do I login to my portfolio?",
        "What are the tax benefits of ELSS funds?",
        "Is it good to invest in debt funds now?",
        "My portfolio performance this year",
        "Difference between direct and regular plans"
    ]
    
    classifier = IntentClassifier()
    
    print("Intent Classification Test Results:")
    print("=" * 60)
    
    for query in test_queries:
        result = classifier.explain_classification(query)
        print(f"Query: {query}")
        print(f"Intent: {result['intent']} (confidence: {result['confidence']:.3f})")
        print(f"Should Retrieve: {result['should_retrieve']}")
        print(f"Reasoning: {result['reasoning']}")
        print("-" * 40)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
