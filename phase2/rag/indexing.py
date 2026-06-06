#!/usr/bin/env python3
"""
Phase 2 — Vector index management and operations.

Handles FAISS index creation, management, and optimization for hybrid retrieval:
- Index building and optimization
- Metadata management and storage
- Index serialization and loading
- Performance monitoring and metrics
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np

from phase2.rag.config import EMBEDDING_MODEL, FAISS_INDEX_TYPE
from .chunking import ChunkMetadata
from .retrieval import HybridRetriever


class VectorIndexManager:
    """Manages vector indexes for hybrid retrieval."""
    
    def __init__(self, embedding_dimension: int = 384):
        """Initialize index manager."""
        self.embedding_dimension = embedding_dimension
        self.index = None
        self.metadata_map = {}
        self.index_stats = {}
    
    def create_optimized_index(
        self,
        embeddings: np.ndarray,
        index_type: str = "ivf",
        nlist: int = 100,
        nprobe: int = 10
    ) -> faiss.Index:
        """Create optimized FAISS index based on data size."""
        n_vectors, dim = embeddings.shape
        
        if index_type == "flat":
            # For small datasets (< 10K vectors)
            index = faiss.IndexFlatIP(dim)
        elif index_type == "ivf":
            # For medium datasets (10K - 1M vectors)
            quantizer = faiss.IndexFlatIP(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, nlist)
            
            # Train index
            print(f"Training IVF index with {n_vectors} vectors...")
            index.train(embeddings.astype(np.float32))
            index.nprobe = nprobe
        elif index_type == "hnsw":
            # For large datasets (> 1M vectors)
            index = faiss.IndexHNSWFlat(dim, 32)
            index.hnsw.efConstruction = 200
            index.hnsw.efSearch = 50
        else:
            raise ValueError(f"Unsupported index type: {index_type}")
        
        # Add embeddings
        print(f"Adding {n_vectors} embeddings to index...")
        start_time = time.time()
        index.add(embeddings.astype(np.float32))
        add_time = time.time() - start_time
        
        # Store stats
        self.index_stats = {
            "index_type": index_type,
            "n_vectors": n_vectors,
            "dimension": dim,
            "nlist": nlist if index_type == "ivf" else None,
            "nprobe": nprobe if index_type == "ivf" else None,
            "add_time_seconds": add_time,
            "memory_usage_mb": self._estimate_memory_usage(index)
        }
        
        self.index = index
        return index
    
    def _estimate_memory_usage(self, index: faiss.Index) -> float:
        """Estimate memory usage in MB."""
        try:
            # FAISS doesn't provide direct memory usage, so we estimate
            n_vectors = index.ntotal
            dim = index.d
            
            if isinstance(index, faiss.IndexFlatIP):
                # Flat index: vectors * dimensions * 4 bytes (float32)
                return (n_vectors * dim * 4) / (1024 * 1024)
            elif isinstance(index, faiss.IndexIVFFlat):
                # IVF index: quantizer + inverted lists
                return (n_vectors * dim * 4) / (1024 * 1024) * 1.2  # Estimate 20% overhead
            elif isinstance(index, faiss.IndexHNSWFlat):
                # HNSW index: vectors + graph structure
                return (n_vectors * dim * 4) / (1024 * 1024) * 1.5  # Estimate 50% overhead
            else:
                return 0.0
        except:
            return 0.0
    
    def save_index(
        self,
        index_path: Path,
        metadata_path: Optional[Path] = None,
        stats_path: Optional[Path] = None
    ) -> None:
        """Save index and metadata to files."""
        if self.index is None:
            raise ValueError("No index to save")
        
        # Save FAISS index
        faiss.write_index(self.index, str(index_path))
        
        # Save metadata if provided
        if metadata_path and self.metadata_map:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata_map, f, indent=2)
        
        # Save stats if provided
        if stats_path and self.index_stats:
            with open(stats_path, 'w', encoding='utf-8') as f:
                json.dump(self.index_stats, f, indent=2)
        
        print(f"Index saved to {index_path}")
        print(f"Stats: {self.index_stats}")
    
    @classmethod
    def load_index(
        cls,
        index_path: Path,
        metadata_path: Optional[Path] = None,
        stats_path: Optional[Path] = None
    ) -> "VectorIndexManager":
        """Load index and metadata from files."""
        manager = cls()
        
        # Load FAISS index
        manager.index = faiss.read_index(str(index_path))
        
        # Load metadata if provided
        if metadata_path and metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                manager.metadata_map = json.load(f)
        
        # Load stats if provided
        if stats_path and stats_path.exists():
            with open(stats_path, 'r', encoding='utf-8') as f:
                manager.index_stats = json.load(f)
        
        print(f"Index loaded from {index_path}")
        print(f"Stats: {manager.index_stats}")
        
        return manager
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        return_scores: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Search index for similar vectors."""
        if self.index is None:
            raise ValueError("No index available for search")
        
        query_embedding = query_embedding.astype(np.float32)
        
        if return_scores:
            scores, indices = self.index.search(query_embedding, top_k)
            return scores, indices
        else:
            _, indices = self.index.search(query_embedding, top_k)
            return None, indices
    
    def get_index_info(self) -> Dict[str, Any]:
        """Get information about the current index."""
        if self.index is None:
            return {"status": "No index loaded"}
        
        info = {
            "status": "Index loaded",
            "ntotal": self.index.ntotal,
            "dimension": self.index.d,
            "is_trained": self.index.is_trained if hasattr(self.index, 'is_trained') else True
        }
        
        # Add type-specific info
        if isinstance(self.index, faiss.IndexIVFFlat):
            info.update({
                "type": "IVF",
                "nlist": self.index.nlist,
                "nprobe": self.index.nprobe
            })
        elif isinstance(self.index, faiss.IndexFlatIP):
            info["type"] = "Flat"
        elif isinstance(self.index, faiss.IndexHNSWFlat):
            info.update({
                "type": "HNSW",
                "ef_construction": self.index.hnsw.efConstruction,
                "ef_search": self.index.hnsw.efSearch
            })
        
        # Add stats
        info.update(self.index_stats)
        
        return info


def build_complete_index(
    chunks_file: Path,
    output_dir: Path,
    index_type: str = FAISS_INDEX_TYPE,
    embedding_model: str = EMBEDDING_MODEL,
) -> Dict[str, Any]:
    """Build complete index from chunks file."""
    from sentence_transformers import SentenceTransformer
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load chunks
    with open(chunks_file, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)
    
    chunks = [item["text"] for item in chunks_data]
    metadata_list = [ChunkMetadata(**item["metadata"]) for item in chunks_data]
    
    print(f"Processing {len(chunks)} chunks for indexing")
    
    # Generate embeddings
    print("Generating embeddings...")
    model = SentenceTransformer(embedding_model)
    embeddings = model.encode(chunks, show_progress_bar=True, normalize_embeddings=True)
    
    # Create index manager
    manager = VectorIndexManager(embedding_dimension=embeddings.shape[1])
    
    # Choose index parameters based on data size
    n_vectors = len(chunks)
    n_vectors = len(chunks)
    if index_type == "ivf" and n_vectors < 1000:
        print(f"Corpus has {n_vectors} vectors — using flat index instead of IVF")
        index_type = "flat"

    if index_type == "ivf":
        nlist = min(100, max(10, n_vectors // 1000))  # Adaptive nlist
        index = manager.create_optimized_index(embeddings, "ivf", nlist=nlist)
    else:
        index = manager.create_optimized_index(embeddings, index_type)
    
    # Create metadata map
    metadata_map = {}
    for i, metadata in enumerate(metadata_list):
        metadata_map[metadata.chunk_id] = metadata.model_dump()
    
    manager.metadata_map = metadata_map
    
    # Save index and metadata
    index_path = output_dir / "vector_index.faiss"
    metadata_path = output_dir / "chunk_metadata.json"
    stats_path = output_dir / "index_stats.json"
    
    manager.save_index(index_path, metadata_path, stats_path)
    
    # Save chunks for BM25
    chunks_output_path = output_dir / "chunks_for_bm25.json"
    with open(chunks_output_path, 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, indent=2)
    
    # Save index config
    config = {
        "embedding_model": embedding_model,
        "embedding_dimension": embeddings.shape[1],
        "total_chunks": len(chunks),
        "index_type": index_type,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC")
    }
    
    config_path = output_dir / "index_config.json"
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    return {
        "index_path": str(index_path),
        "chunks_path": str(chunks_output_path),
        "config_path": str(config_path),
        "stats": manager.get_index_info()
    }


def main() -> int:
    """Main function for index building."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 2 - Vector index management")
    parser.add_argument("--chunks", type=Path, required=True, help="Chunks JSON file")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory")
    parser.add_argument("--index-type", type=str, default=FAISS_INDEX_TYPE, choices=["flat", "ivf", "hnsw"])
    parser.add_argument("--model", type=str, default=EMBEDDING_MODEL)
    
    args = parser.parse_args()
    
    # Build index
    result = build_complete_index(
        chunks_file=args.chunks,
        output_dir=args.output_dir,
        index_type=args.index_type,
        embedding_model=args.model
    )
    
    print(f"\nIndex building completed!")
    print(f"Index saved to: {result['index_path']}")
    print(f"Chunks saved to: {result['chunks_path']}")
    print(f"Config saved to: {result['config_path']}")
    print(f"\nIndex stats:")
    for key, value in result['stats'].items():
        print(f"  {key}: {value}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
