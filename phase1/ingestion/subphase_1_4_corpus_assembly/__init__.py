"""Phase 1.4 — corpus assembly and manifest metadata."""

from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import (
    CORPUS_FILENAME,
    INGEST_MANIFEST_FILENAME,
    AssemblyResult,
    assemble_corpus,
    extract_scheme_names,
)

__all__ = [
    "CORPUS_FILENAME",
    "INGEST_MANIFEST_FILENAME",
    "AssemblyResult",
    "assemble_corpus",
    "extract_scheme_names",
]
