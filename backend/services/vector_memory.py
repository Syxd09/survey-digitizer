"""
Hydra v12.5 — Vector Memory Layer
===================================
Semantic recall using FAISS + Sentence-Transformers.
Embedding-based retrieval with cosine similarity thresholding.

Features:
  - Cosine similarity (not L2 distance) for better threshold control
  - Multi-field correction context
  - Confidence-based acceptance (only apply when similarity > 0.92)
"""

import faiss
import numpy as np
import logging
import os
import pickle
from sentence_transformers import SentenceTransformer
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class VectorMemory:
    SIMILARITY_THRESHOLD = 0.92  # Only apply corrections above this

    def __init__(
        self,
        model_name: str = "paraphrase-MiniLM-L3-v2",
        index_path: str = "backend/feedback_loop/vector_index.faiss",
    ):
        self.device = "cpu"
        self.model = SentenceTransformer(model_name, device=self.device)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.index_path = index_path
        self.metadata_path = index_path + ".meta"

        # Use IndexFlatIP for cosine similarity (inner product on normalized vectors)
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
            with open(self.metadata_path, "rb") as f:
                self.metadata = pickle.load(f)
            logger.info(f"[MEMORY] Loaded index with {self.index.ntotal} vectors.")
        else:
            self.index = faiss.IndexFlatIP(self.dim)  # Inner Product for cosine sim
            self.metadata: List[Dict] = []
            logger.info("[MEMORY] Created fresh vector index.")

    def add_feedback(self, raw_text: str, corrected_text: str, context: Optional[Dict] = None):
        """
        Store a correction in the vector space with full context.
        """
        embedding = self._encode(raw_text)
        self.index.add(embedding)
        self.metadata.append({
            "raw": raw_text,
            "correction": corrected_text,
            "context": context or {},
        })
        self.save()
        logger.info(f"[MEMORY] Stored correction: '{raw_text[:50]}...' → '{corrected_text[:50]}...'")

    def search(self, text: str) -> Optional[str]:
        """
        Retrieve a semantic correction if cosine similarity exceeds threshold.
        Returns the corrected text, or None if no good match.
        """
        if self.index.ntotal == 0:
            return None

        embedding = self._encode(text)
        D, I = self.index.search(embedding, k=1)

        # D[0][0] is cosine similarity (higher is better, max=1.0)
        similarity = float(D[0][0])

        if similarity >= self.SIMILARITY_THRESHOLD:
            match = self.metadata[I[0][0]]
            logger.info(
                f"[MEMORY] Match found (sim={similarity:.3f}): "
                f"'{text[:40]}' → '{match['correction'][:40]}'"
            )
            return match["correction"]

        return None

    def search_with_context(self, text: str, k: int = 3) -> List[Dict]:
        """
        Retrieve top-k matches with full context.
        Useful for multi-field correction.
        """
        if self.index.ntotal == 0:
            return []

        embedding = self._encode(text)
        D, I = self.index.search(embedding, k=min(k, self.index.ntotal))

        results = []
        for i in range(len(I[0])):
            idx = I[0][i]
            sim = float(D[0][i])
            if sim >= self.SIMILARITY_THRESHOLD * 0.9:  # Slightly relaxed for context
                results.append({
                    **self.metadata[idx],
                    "similarity": sim,
                })

        return results

    def _encode(self, text: str) -> np.ndarray:
        """Encode text to normalized embedding (for cosine similarity via IP)."""
        embedding = self.model.encode([text])
        # Normalize for cosine similarity via inner product
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding.astype("float32")

    def save(self):
        """Persist index and metadata to disk."""
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)


def get_vector_memory():
    os.makedirs("backend/feedback_loop", exist_ok=True)
    return VectorMemory()
