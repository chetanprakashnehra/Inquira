import logging
from typing import List, Dict, Any, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Re-ranks retrieved query-document pairs using a Cross-Encoder transformer."""

    def __init__(self):
        self.model_name = settings.RERANKER_MODEL
        self.threshold = settings.RERANKER_SCORE_THRESHOLD
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Loaded CrossEncoder model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformers CrossEncoder ({e}). Using lexical-semantic scoring fallback.")
                self._model = "fallback"

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Score (query, chunk_text) pairs and return top_k reranked results.
        """
        if not candidates:
            return []

        top_k = top_k or settings.TOP_K_RERANKED
        self._load_model()

        chunk_texts = [
            c.get("payload", {}).get("content", "") or c.get("content", "")
            for c in candidates
        ]

        if self._model and self._model != "fallback":
            try:
                pairs = [[query, text] for text in chunk_texts]
                scores = self._model.predict(pairs)
                
                scored_candidates = []
                for idx, score in enumerate(scores):
                    item = candidates[idx].copy()
                    item["rerank_score"] = float(score)
                    scored_candidates.append(item)

                # Sort by score descending
                scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
                
                # Filter by threshold if applicable (or take top_k)
                filtered = [c for c in scored_candidates if c["rerank_score"] >= self.threshold]
                return filtered[:top_k] if filtered else scored_candidates[:top_k]
            except Exception as e:
                logger.error(f"Error during CrossEncoder prediction: {e}")

        # Fallback scoring: RRF score + token overlap heuristic
        scored_candidates = []
        query_tokens = set(query.lower().split())
        for idx, candidate in enumerate(candidates):
            text = chunk_texts[idx].lower()
            overlap = sum(1 for token in query_tokens if token in text) / (len(query_tokens) or 1)
            rrf_score = candidate.get("rrf_score", 0.0)
            combined_score = (rrf_score * 10) + (overlap * 0.5)
            
            item = candidate.copy()
            item["rerank_score"] = combined_score
            scored_candidates.append(item)

        scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_candidates[:top_k]


reranker = CrossEncoderReranker()
