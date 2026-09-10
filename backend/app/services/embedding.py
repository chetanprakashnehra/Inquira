import os
import logging
from typing import List, Dict, Any, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Provides dense and sparse vector generation for hybrid retrieval."""

    def __init__(self):
        self.dense_model_name = settings.DENSE_EMBEDDING_MODEL
        self.openai_api_key = settings.OPENAI_API_KEY
        self._fastembed_dense = None
        self._fastembed_sparse = None

    def get_dense_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector embeddings for a list of texts."""
        if not texts:
            return []

        # 1. Use OpenAI if key is configured and valid
        if self.openai_api_key and self.openai_api_key.startswith("sk-"):
            try:
                from langchain_openai import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings(
                    model=self.dense_model_name,
                    openai_api_key=self.openai_api_key
                )
                return embeddings.embed_documents(texts)
            except Exception as e:
                logger.warning(f"OpenAI embedding generation failed ({e}), falling back to local FastEmbed.")

        # 2. Local fallback using FastEmbed TextEmbedding
        try:
            if self._fastembed_dense is None:
                from fastembed import TextEmbedding
                self._fastembed_dense = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            embeddings_generator = self._fastembed_dense.embed(texts)
            return [list(emb) for emb in embeddings_generator]
        except Exception as e:
            logger.error(f"FastEmbed dense embedding generation error: {e}")
            # Mock fallback with deterministically seeded vectors for testing / dry runs
            import hashlib
            results = []
            for t in texts:
                h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
                # create dimension vector
                dim = settings.DENSE_EMBEDDING_DIM
                vec = [((h >> (i % 32)) & 0xFF) / 255.0 for i in range(dim)]
                # normalize
                norm = sum(x * x for x in vec) ** 0.5 or 1.0
                results.append([x / norm for x in vec])
            return results

    def get_sparse_embeddings(self, texts: List[str]) -> List[Dict[int, float]]:
        """Generate sparse BM25 vectors (dictionary of {index: weight}) for Qdrant sparse vectors."""
        if not texts:
            return []

        try:
            if self._fastembed_sparse is None:
                from fastembed import SparseTextEmbedding
                self._fastembed_sparse = SparseTextEmbedding(model_name="Qdrant/bm25")
            embeddings_generator = self._fastembed_sparse.embed(texts)
            results = []
            for sparse_vec in embeddings_generator:
                # sparse_vec has .indices and .values
                sparse_dict = {int(idx): float(val) for idx, val in zip(sparse_vec.indices, sparse_vec.values)}
                results.append(sparse_dict)
            return results
        except Exception as e:
            logger.warning(f"FastEmbed sparse generation unavailable or error ({e}), using simple lexical token frequency.")
            results = []
            for text in texts:
                words = text.lower().split()
                tf: Dict[int, float] = {}
                for w in words:
                    idx = abs(hash(w)) % 100000
                    tf[idx] = tf.get(idx, 0.0) + 1.0
                # normalize
                total = len(words) or 1
                results.append({k: v / total for k, v in tf.items()})
            return results

    def get_query_dense_embedding(self, query: str) -> List[float]:
        """Generate dense embedding for single query."""
        results = self.get_dense_embeddings([query])
        return results[0] if results else []

    def get_query_sparse_embedding(self, query: str) -> Dict[int, float]:
        """Generate sparse BM25 embedding for single query."""
        results = self.get_sparse_embeddings([query])
        return results[0] if results else {}


embedding_service = EmbeddingService()
