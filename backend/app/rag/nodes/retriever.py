import logging
from typing import Dict, Any, List
from app.rag.state import AgentState
from app.services.embedding import embedding_service
from app.rag.retrieval.qdrant_client import qdrant_store
from app.rag.retrieval.rrf import ReciprocalRankFusion
from app.rag.retrieval.reranker import reranker
from app.config import settings

logger = logging.getLogger(__name__)


class HybridRetrieverNode:
    """Stage 2: 5-Technique Hybrid Retrieval (Dense + BM25 + RRF + Cross-Encoder + HyDE)."""

    def retrieve(self, state: AgentState) -> Dict[str, Any]:
        user_id = state.get("user_id")
        kb_id = state.get("knowledge_base_id")
        query = state.get("rewritten_query") or state.get("query", "")
        hyde_doc = state.get("hyde_document") or query

        # 1. HyDE Embedding: Embed the hypothetical document + query combination
        search_dense_query = f"{query}\n{hyde_doc}" if hyde_doc != query else query
        dense_vec = embedding_service.get_query_dense_embedding(search_dense_query)

        # 2. Dense Vector Search (Qdrant)
        dense_results = qdrant_store.search_dense(
            query_vector=dense_vec,
            user_id=user_id,
            knowledge_base_id=kb_id,
            limit=settings.TOP_K_DENSE
        )

        # 3. Sparse / BM25 Search (Qdrant)
        sparse_vec = embedding_service.get_query_sparse_embedding(query)
        sparse_results = qdrant_store.search_sparse(
            sparse_query=sparse_vec,
            user_id=user_id,
            knowledge_base_id=kb_id,
            limit=settings.TOP_K_SPARSE
        )

        # 4. Reciprocal Rank Fusion (RRF)
        fused_candidates = ReciprocalRankFusion.fuse(
            ranked_lists=[dense_results, sparse_results],
            k=settings.RRF_K,
            top_n=settings.TOP_K_FUSED
        )

        # 5. Cross-Encoder Re-ranking
        ranked_chunks = reranker.rerank(
            query=query,
            candidates=fused_candidates,
            top_k=settings.TOP_K_RERANKED
        )

        logger.info(
            f"Retrieval complete: {len(dense_results)} dense, {len(sparse_results)} sparse, "
            f"{len(fused_candidates)} fused, {len(ranked_chunks)} top reranked chunks."
        )

        return {
            "retrieved_dense": dense_results,
            "retrieved_sparse": sparse_results,
            "fused_candidates": fused_candidates,
            "ranked_chunks": ranked_chunks
        }


retriever_node = HybridRetrieverNode()
