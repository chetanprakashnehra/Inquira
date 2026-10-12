import re
from uuid import UUID

from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
)
from sentence_transformers import CrossEncoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from embeddings import embed_text
from models import Document, DocumentChunk


# ============================================================
# QDRANT
# ============================================================

qdrant_client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)


_named_vectors_cache: bool | None = None


def get_using_param():
    global _named_vectors_cache
    if _named_vectors_cache is None:
        try:
            col = qdrant_client.get_collection(settings.qdrant_collection_name)
            _named_vectors_cache = isinstance(col.config.params.vectors, dict) and "dense" in col.config.params.vectors
        except Exception:
            _named_vectors_cache = True
    return "dense" if _named_vectors_cache else None


# ============================================================
# DENSE RETRIEVAL
# ============================================================

def dense_search(
    query_vector: list[float],
    knowledge_base_id: str,
    limit: int = 10,
):
    """
    Search Qdrant using vector similarity.
    """

    using_param = get_using_param()
    query_kwargs = {
        "collection_name": settings.qdrant_collection_name,
        "query": query_vector,
        "query_filter": Filter(
            must=[
                FieldCondition(
                    key="knowledge_base_id",
                    match=MatchValue(
                        value=knowledge_base_id
                    ),
                )
            ]
        ),
        "limit": limit,
        "with_payload": True,
    }
    if using_param:
        query_kwargs["using"] = using_param

    results = qdrant_client.query_points(**query_kwargs)

    return results.points


# ============================================================
# BM25 RETRIEVER
# ============================================================

class BM25Retriever:

    def __init__(
        self,
        documents: list[dict],
    ):

        self.documents = documents

        tokenized_documents = [
            self._tokenize(
                document["content"]
            )
            for document in documents
        ]

        self.bm25 = BM25Okapi(
            tokenized_documents
        )

    def search(
        self,
        query: str,
        limit: int = 10,
    ):

        query_tokens = self._tokenize(
            query
        )

        scores = self.bm25.get_scores(
            query_tokens
        )

        ranked_indexes = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )

        results = []

        for index in ranked_indexes[:limit]:

            document = self.documents[index]

            results.append(
                {
                    "chunk_id": document["id"],
                    "document_id": document.get(
                        "document_id"
                    ),
                    "content": document["content"],
                    "source": document.get(
                        "source"
                    ),
                    "page": document.get(
                        "page"
                    ),
                    "score": float(
                        scores[index]
                    ),
                    "rank": len(results) + 1,
                }
            )

        return results

    @staticmethod
    def _tokenize(text: str):

        return re.findall(
            r"\b\w+\b",
            text.lower(),
        )


# ============================================================
# RECIPROCAL RANK FUSION
# ============================================================

def reciprocal_rank_fusion(
    dense_results,
    bm25_results,
    k: int = 60,
):

    scores = {}
    data = {}

    # --------------------------------------------------------
    # Dense results
    # --------------------------------------------------------

    for rank, result in enumerate(
        dense_results,
        start=1,
    ):

        payload = result.payload or {}

        chunk_id = payload.get(
            "chunk_id"
        )

        if not chunk_id:
            continue

        scores[chunk_id] = (
            scores.get(chunk_id, 0)
            + 1 / (k + rank)
        )

        data[chunk_id] = {
            "chunk_id": chunk_id,
            "document_id": payload.get(
                "document_id"
            ),
            "content": payload.get(
                "text",
                "",
            ),
            "source": payload.get(
                "source"
            ),
            "page": payload.get(
                "page"
            ),
        }

    # --------------------------------------------------------
    # BM25 results
    # --------------------------------------------------------

    for result in bm25_results:

        chunk_id = result["chunk_id"]

        rank = result["rank"]

        scores[chunk_id] = (
            scores.get(chunk_id, 0)
            + 1 / (k + rank)
        )

        if chunk_id not in data:

            data[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": result.get(
                    "document_id"
                ),
                "content": result[
                    "content"
                ],
                "source": result.get(
                    "source"
                ),
                "page": result.get(
                    "page"
                ),
            }

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    results = []

    for chunk_id, score in ranked:

        results.append(
            {
                **data[chunk_id],
                "score": score,
            }
        )

    return results


# ============================================================
# RERANKER
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            _reranker = CrossEncoder(
                settings.reranker_model
            )
        except Exception as exc:
            print(f"[RERANKER] Failed to load CrossEncoder ({exc}), using fallback ranking")
            return None
    return _reranker


def rerank(
    query: str,
    results: list[dict],
    limit: int = 5,
):

    if not results:
        return []

    reranker_instance = get_reranker()
    if reranker_instance is None:
        return results[:limit]

    pairs = [
        (
            query,
            result["content"],
        )
        for result in results
    ]

    scores = reranker_instance.predict(
        pairs
    )

    reranked = []

    for result, score in zip(
        results,
        scores,
    ):

        reranked.append(
            {
                **result,
                "rerank_score": float(
                    score
                ),
            }
        )

    reranked.sort(
        key=lambda item: item[
            "rerank_score"
        ],
        reverse=True,
    )

    return reranked[:limit]


# ============================================================
# COMPLETE RETRIEVAL PIPELINE
# ============================================================

async def retrieve_documents(
    question: str,
    knowledge_base_id: str,
    db: AsyncSession,
    dense_limit: int = 10,
    bm25_limit: int = 10,
    final_limit: int = 5,
):

    # --------------------------------------------------------
    # 1. Embed the question
    # --------------------------------------------------------

    query_vector = embed_text(
        question
    )

    # --------------------------------------------------------
    # 2. Dense retrieval
    # --------------------------------------------------------

    dense_results = dense_search(
        query_vector=query_vector,
        knowledge_base_id=knowledge_base_id,
        limit=dense_limit,
    )

    # --------------------------------------------------------
    # 3. Get chunks from PostgreSQL
    # --------------------------------------------------------

    result = await db.execute(
        select(
            DocumentChunk,
            Document,
        )
        .join(
            Document,
            DocumentChunk.document_id
            == Document.id,
        )
        .where(
            Document.knowledge_base_id
            == UUID(knowledge_base_id)
        )
    )

    rows = result.all()

    documents = []

    for chunk, document in rows:

        documents.append(
            {
                "id": str(chunk.id),
                "document_id": str(
                    document.id
                ),
                "content": chunk.content,
                "source": document.filename,
                "page": chunk.page_number,
            }
        )

    # --------------------------------------------------------
    # 4. BM25 retrieval
    # --------------------------------------------------------

    if documents:

        bm25_retriever = BM25Retriever(
            documents
        )

        bm25_results = (
            bm25_retriever.search(
                question,
                limit=bm25_limit,
            )
        )

    else:

        bm25_results = []

    # --------------------------------------------------------
    # 5. Combine dense + BM25
    # --------------------------------------------------------

    combined_results = (
        reciprocal_rank_fusion(
            dense_results=dense_results,
            bm25_results=bm25_results,
        )
    )

    # --------------------------------------------------------
    # 6. Rerank
    # --------------------------------------------------------

    final_results = rerank(
        query=question,
        results=combined_results,
        limit=final_limit,
    )

    return final_results