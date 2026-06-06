#!/usr/bin/env python3
"""
Phase 2 — Smart chunking strategy with metadata enrichment.

Implements intelligent chunking optimized for sparse financial data with:
- 300-500 character chunks with semantic boundaries
- Metadata enrichment with financial density scoring
- Entity extraction and tagging
- Navigation content filtering using Phase 1.5 validation scores
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from phase2.rag.config import (
    CHUNK_OVERLAP,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    MIN_FINANCIAL_DENSITY,
    MIN_SOURCE_VALIDATION_QUALITY,
)
from phase2.rag.fund_records import (
    detect_query_metric,
    extract_amc_summary,
    format_amc_summary,
    format_unified_fund_record,
    fund_name_matches,
    merge_fund_records,
    parse_detail_blocks,
    parse_scheme_table,
)

try:
    import spacy

    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None


def sent_tokenize(text: str) -> list[str]:
    """Lightweight sentence split (no NLTK dependency)."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


class ChunkMetadata(BaseModel):
    """Metadata for each chunk."""
    chunk_id: str = Field(description="Unique chunk identifier")
    source_id: str = Field(description="Corpus source id (groww_amc_*)")
    source_url: str = Field(description="Original source URL")
    amc_name: str = Field(description="AMC name")
    content_type: str = Field(description="Type: fund_info|navigation|calculator|mixed")
    entities: List[str] = Field(default_factory=list, description="Extracted entities")
    financial_density: float = Field(description="Financial content density (0-1)")
    text_length: int = Field(description="Character count")
    chunk_index: int = Field(description="Index within source")
    total_chunks: int = Field(description="Total chunks in source")
    ingested_at: str = Field(description="Source ingestion timestamp")


class SmartChunker:
    """Smart chunking strategy for financial corpus data."""
    
    def __init__(
        self,
        min_chunk_size: int = MIN_CHUNK_SIZE,
        max_chunk_size: int = MAX_CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
        financial_keywords: Optional[List[str]] = None,
    ):
        """Initialize the smart chunker."""
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.nlp = nlp
        
        # Financial keywords for density calculation
        self.financial_keywords = financial_keywords or [
            "mutual fund", "NAV", "net asset value", "scheme", "performance", "returns",
            "expense ratio", "exit load", "SIP", "systematic investment plan", "lump sum",
            "fund manager", "AUM", "assets under management", "risk", "portfolio", "equity",
            "debt", "hybrid", "index fund", "ELSS", "tax saving", "dividend", "growth",
            "direct plan", "regular plan", "benchmark", "category", "rating", "crisil"
        ]
        
        # Navigation keywords for filtering
        self.navigation_keywords = [
            "invest in stocks", "IPO", "demat account", "trading", "futures", "options",
            "commodities", "API trading", "terminal", "watchlist", "screener", "chart",
            "calculator", "brokerage", "margin", "pledge", "intraday", "ETF screener"
        ]
    
    def extract_entities(self, text: str) -> List[str]:
        """Extract financial entities from text."""
        entities = []
        
        if self.nlp:
            doc = self.nlp(text)
            # Extract named entities
            for ent in doc.ents:
                if ent.label_ in ["ORG", "PRODUCT", "MONEY", "PERCENT"]:
                    entities.append(ent.text)
        
        # Extract financial keywords
        for keyword in self.financial_keywords:
            if keyword.lower() in text.lower():
                entities.append(keyword)
        
        # Extract fund names (pattern matching)
        fund_patterns = [
            r'\w+\s+(?:Index\s+Fund|Fund|Direct\s+Plan|Regular\s+Plan|Growth|Dividend)',
            r'\w+\s+(?:Nifty|Sensex|Bank|IT|Pharma|Auto)\s+\w+',
        ]
        
        for pattern in fund_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.extend(matches)
        
        return list(set(entities))

    @staticmethod
    def trim_nav_prefix(text: str, amc_name: str) -> str:
        """Skip Groww nav boilerplate; start at scheme listing when present."""
        prefix = amc_name.replace(" Mutual Fund", "").strip()
        for marker in (f"List of {amc_name}", f"List of {prefix}"):
            idx = text.find(marker)
            if idx >= 0:
                return text[idx:]
        return text

    def calculate_financial_density(self, text: str) -> float:
        """Calculate financial content density (0-1)."""
        text_lower = text.lower()
        financial_count = sum(1 for keyword in self.financial_keywords if keyword in text_lower)
        navigation_count = sum(1 for keyword in self.navigation_keywords if keyword in text_lower)
        
        total_words = len(text.split())
        if total_words == 0:
            return 0.0
        
        # Density based on financial keywords vs total words, penalized by navigation
        financial_score = financial_count / total_words
        navigation_penalty = navigation_count / total_words if total_words > 0 else 0
        
        return max(0.0, financial_score - navigation_penalty)
    
    def classify_content_type(self, text: str) -> str:
        """Classify content type based on keywords and density."""
        financial_density = self.calculate_financial_density(text)
        navigation_density = sum(1 for keyword in self.navigation_keywords if keyword.lower() in text.lower()) / len(text.split())
        
        if financial_density > 0.1:
            return "fund_info"
        elif navigation_density > 0.2:
            return "navigation"
        elif "calculator" in text.lower() or "calculate" in text.lower():
            return "calculator"
        else:
            return "mixed"
    
    def find_semantic_boundaries(self, text: str) -> List[int]:
        """Find semantic boundaries for chunk splitting."""
        boundaries = []
        
        # Split by sentences first
        sentences = sent_tokenize(text)
        
        current_length = 0
        for i, sentence in enumerate(sentences):
            current_length += len(sentence)
            
            # Check if we should create a boundary
            if current_length >= self.min_chunk_size:
                # Prefer boundaries at sentence ends
                if current_length <= self.max_chunk_size:
                    boundaries.append(i + 1)
                    current_length = 0
                else:
                    # Force boundary if too long
                    boundaries.append(i)
                    current_length = len(sentence)
        
        return boundaries
    
    def _build_chunk_metadata(
        self,
        chunk_text: str,
        *,
        chunk_id: str,
        source_id: str,
        source_url: str,
        amc_name: str,
        chunk_index: int,
        ingested_at: str,
        extra_entities: list[str] | None = None,
    ) -> ChunkMetadata:
        entities = self.extract_entities(chunk_text)
        if extra_entities:
            entities = list(set(entities + extra_entities))
        return ChunkMetadata(
            chunk_id=chunk_id,
            source_id=source_id,
            source_url=source_url,
            amc_name=amc_name,
            content_type=self.classify_content_type(chunk_text),
            entities=entities,
            financial_density=self.calculate_financial_density(chunk_text),
            text_length=len(chunk_text),
            chunk_index=chunk_index,
            total_chunks=0,
            ingested_at=ingested_at,
        )

    def create_fund_centric_chunks(
        self,
        text: str,
        source_id: str,
        source_url: str,
        amc_name: str,
        chunk_id_prefix: str,
        ingested_at: str,
    ) -> List[Tuple[str, ChunkMetadata]]:
        """Create one chunk per fund table row and per scheme detail block."""
        text = self.trim_nav_prefix(text, amc_name)
        if not text.strip():
            return []

        chunks: List[Tuple[str, ChunkMetadata]] = []
        chunk_index = 0

        summary = extract_amc_summary(text, amc_name)
        if summary:
            summary_text = format_amc_summary(summary)
            meta = self._build_chunk_metadata(
                summary_text,
                chunk_id=f"{chunk_id_prefix}_chunk_{chunk_index:03d}",
                source_id=source_id,
                source_url=source_url,
                amc_name=amc_name,
                chunk_index=chunk_index,
                ingested_at=ingested_at,
                extra_entities=[amc_name, "AUM", "overview"],
            )
            chunks.append((summary_text, meta))
            chunk_index += 1

        for record in merge_fund_records(
            parse_scheme_table(text),
            parse_detail_blocks(text),
            amc_name=amc_name,
            source_id=source_id,
            source_url=source_url,
            ingested_at=ingested_at,
        ):
            chunk_text = format_unified_fund_record(record)
            meta = self._build_chunk_metadata(
                chunk_text,
                chunk_id=f"{chunk_id_prefix}_chunk_{chunk_index:03d}",
                source_id=source_id,
                source_url=source_url,
                amc_name=amc_name,
                chunk_index=chunk_index,
                ingested_at=ingested_at,
                extra_entities=[
                    record["fund_name"],
                    "NAV",
                    "AUM",
                    "Expense Ratio",
                    "SIP",
                    "Returns",
                ],
            )
            chunks.append((chunk_text, meta))
            chunk_index += 1

        for _, meta in chunks:
            meta.total_chunks = len(chunks)
        return chunks

    def create_chunks_with_metadata(
        self,
        text: str,
        source_id: str,
        source_url: str,
        amc_name: str,
        chunk_id_prefix: str,
        ingested_at: str,
    ) -> List[Tuple[str, ChunkMetadata]]:
        """Create chunks with rich metadata (fund-centric when table data exists)."""
        fund_chunks = self.create_fund_centric_chunks(
            text=text,
            source_id=source_id,
            source_url=source_url,
            amc_name=amc_name,
            chunk_id_prefix=chunk_id_prefix,
            ingested_at=ingested_at,
        )
        if fund_chunks:
            return fund_chunks

        text = self.trim_nav_prefix(text, amc_name)
        if not text.strip():
            return []

        sentences = sent_tokenize(text)
        if not sentences:
            return []

        chunks: List[Tuple[str, ChunkMetadata]] = []
        start = 0
        chunk_index = 0

        while start < len(sentences):
            current: list[str] = []
            length = 0
            end = start

            while end < len(sentences):
                sentence = sentences[end]
                if length + len(sentence) > self.max_chunk_size and current:
                    break
                current.append(sentence)
                length += len(sentence)
                end += 1
                if length >= self.min_chunk_size:
                    break

            chunk_text = " ".join(current).strip()
            if len(chunk_text) >= self.min_chunk_size:
                meta = self._build_chunk_metadata(
                    chunk_text,
                    chunk_id=f"{chunk_id_prefix}_chunk_{chunk_index:03d}",
                    source_id=source_id,
                    source_url=source_url,
                    amc_name=amc_name,
                    chunk_index=chunk_index,
                    ingested_at=ingested_at,
                )
                chunks.append((chunk_text, meta))
                chunk_index += 1

            if end >= len(sentences):
                break

            # Overlap: rewind by characters approximated as sentences
            overlap_chars = 0
            overlap_start = end
            while overlap_start > start and overlap_chars < self.overlap:
                overlap_start -= 1
                overlap_chars += len(sentences[overlap_start])
            start = max(start + 1, overlap_start)

        for _, meta in chunks:
            meta.total_chunks = len(chunks)
        return chunks
    
    def process_corpus_run(
        self,
        run_dir: Path,
        validation_report: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, ChunkMetadata]]:
        """Process an entire corpus run and create chunks."""
        chunks = []
        
        # Load ingest manifest
        manifest_path = run_dir / "ingest_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        # Load validation report if available
        validation_scores = {}
        if validation_report:
            validation_scores = {
                source_id: result.get("metrics", {}).get("content_quality", 0.0)
                for source_id, result in validation_report.get("sources", {}).items()
            }
        
        # Process each source
        for source in manifest["sources"]:
            if not source.get("fetch_ok", False):
                continue
            
            source_id = source["id"]
            amc_name = source["amc_name"]
            source_url = source["canonical_url"]
            ingested_at = source.get("fetched_at_utc") or manifest["created_at_utc"]
            
            # Get validation score
            validation_score = validation_scores.get(source_id, 0.0)
            
            # Skip low-quality sources
            if validation_score < MIN_SOURCE_VALIDATION_QUALITY:
                continue
            
            # Read clean text
            clean_text_path = run_dir / source_id / "clean.txt"
            if not clean_text_path.exists():
                continue
            
            with open(clean_text_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Create chunks
            source_chunks = self.create_chunks_with_metadata(
                text=text,
                source_id=source_id,
                source_url=source_url,
                amc_name=amc_name,
                chunk_id_prefix=source_id,
                ingested_at=ingested_at,
            )
            
            chunks.extend(source_chunks)
        
        return chunks
    
    def filter_chunks_by_quality(
        self,
        chunks: List[Tuple[str, ChunkMetadata]],
        min_financial_density: float = MIN_FINANCIAL_DENSITY,
        max_navigation_ratio: float = 0.3,
    ) -> List[Tuple[str, ChunkMetadata]]:
        """Filter chunks based on quality metrics."""
        filtered_chunks = []
        
        for text, metadata in chunks:
            # Filter by financial density
            if metadata.financial_density < min_financial_density:
                continue
            
            # Filter out navigation-heavy content
            if metadata.content_type == "navigation":
                continue
            
            # Filter calculator content (low informational value)
            if metadata.content_type == "calculator":
                continue
            
            filtered_chunks.append((text, metadata))
        
        return filtered_chunks
    
    def save_chunks(
        self,
        chunks: List[Tuple[str, ChunkMetadata]],
        output_dir: Path
    ) -> Dict[str, Any]:
        """Save chunks and metadata to output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save chunks
        chunks_data = []
        for text, metadata in chunks:
            chunks_data.append({
                "text": text,
                "metadata": metadata.model_dump(),
            })
        
        chunks_file = output_dir / "chunks.json"
        with open(chunks_file, 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, indent=2)
        
        # Save metadata summary
        summary = {
            "total_chunks": len(chunks),
            "average_chunk_size": sum(len(text) for text, _ in chunks) / len(chunks) if chunks else 0,
            "content_types": {},
            "amc_distribution": {},
            "average_financial_density": sum(meta.financial_density for _, meta in chunks) / len(chunks) if chunks else 0
        }
        
        # Calculate distributions
        for _, metadata in chunks:
            summary["content_types"][metadata.content_type] = summary["content_types"].get(metadata.content_type, 0) + 1
            summary["amc_distribution"][metadata.amc_name] = summary["amc_distribution"].get(metadata.amc_name, 0) + 1
        
        summary_file = output_dir / "chunking_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        return {
            "chunks_file": str(chunks_file),
            "summary_file": str(summary_file),
            "summary": summary
        }


def main() -> int:
    """Main function for chunking corpus data."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 2 - Smart chunking")
    parser.add_argument("--run-dir", type=Path, required=True, help="Corpus run directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory for chunks")
    parser.add_argument("--validation-report", type=Path, help="Validation report JSON")
    parser.add_argument("--min-density", type=float, default=MIN_FINANCIAL_DENSITY)
    parser.add_argument("--min-size", type=int, default=MIN_CHUNK_SIZE)
    parser.add_argument("--max-size", type=int, default=MAX_CHUNK_SIZE)
    
    args = parser.parse_args()
    
    # Initialize chunker
    chunker = SmartChunker(
        min_chunk_size=args.min_size,
        max_chunk_size=args.max_size
    )
    
    # Load validation report if provided
    validation_report = None
    if args.validation_report and args.validation_report.exists():
        with open(args.validation_report, 'r', encoding='utf-8') as f:
            validation_report = json.load(f)
    
    # Process corpus
    print(f"Processing corpus run: {args.run_dir}")
    chunks = chunker.process_corpus_run(args.run_dir, validation_report)
    print(f"Created {len(chunks)} chunks before filtering")
    
    # Filter by quality
    filtered_chunks = chunker.filter_chunks_by_quality(
        chunks,
        min_financial_density=args.min_density
    )
    print(f"Filtered to {len(filtered_chunks)} high-quality chunks")
    
    # Save chunks
    output_dir = args.output_dir or args.run_dir / "chunks"
    result = chunker.save_chunks(filtered_chunks, output_dir)
    
    print(f"Chunks saved to: {result['chunks_file']}")
    print(f"Summary saved to: {result['summary_file']}")
    print(f"Average financial density: {result['summary']['average_financial_density']:.3f}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
