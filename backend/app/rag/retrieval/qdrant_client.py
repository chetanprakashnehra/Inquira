import uuid
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient, models
from app.config import settings

logger = logging.getLogger(__name__)


class QdrantStore:
    """Manages dense and sparse vector storage and retrieval in Qdrant."""

    def __init__(self):
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.dense_dim = settings.DENSE_EMBEDDING_DIM
        self._client = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._init_client()
        return self._client

    def _init_client(self):
        try:
            if settings.QDRANT_URL.startswith("http"):
                self._client = QdrantClient(
                    url=settings.QDRANT_URL,
                    api_key=settings.QDRANT_API_KEY,
                    timeout=5.0,
                    check_compatibility=False
                )
            else:
                self._client = QdrantClient(":memory:")
            self._ensure_collection()
        except Exception as e:
            if settings.ENVIRONMENT == "development":
                logger.warning(f"Could not connect to Qdrant at {settings.QDRANT_URL}: {e}. Initializing in-memory fallback.")
                self._client = QdrantClient(":memory:")
                self._ensure_collection()
            else:
                raise RuntimeError(f"Could not connect to Qdrant in production: {e}")


    def _ensure_collection(self):
        """Ensure the collection and payload indexes exist."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense": models.VectorParams(
                            size=self.dense_dim,
                            distance=models.Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        "bm25": models.SparseVectorParams(
                            index=models.SparseIndexParams(on_disk=False)
                        )
                    }
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")

            for field in ["user_id", "knowledge_base_id", "document_id"]:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error ensuring Qdrant collection: {e}")

    def upsert_chunks(
        self,
        point_ids: List[str],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[int, float]],
        payloads: List[Dict[str, Any]]
    ) -> bool:
        """Upsert dense and sparse points into Qdrant."""
        points = []
        for i in range(len(point_ids)):
            sparse_dict = sparse_vectors[i] if i < len(sparse_vectors) else {}
            indices = list(sparse_dict.keys())
            values = list(sparse_dict.values())
            
            p = models.PointStruct(
                id=point_ids[i],
                vector={
                    "dense": dense_vectors[i],
                    "bm25": models.SparseVector(indices=indices, values=values)
                },
                payload=payloads[i]
            )
            points.append(p)

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            return True
        except Exception as e:
            logger.error(f"Qdrant upsert error: {e}")
            raise

    def search_dense(
        self,
        query_vector: List[float],
        user_id: str,
        knowledge_base_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Perform dense vector search with payload filtering."""
        filter_conditions = models.Filter(
            must=[
                models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id))),
                models.FieldCondition(key="knowledge_base_id", match=models.MatchValue(value=str(knowledge_base_id))),
            ]
        )

        try:
            # Try query_points (Qdrant client >= 1.10)
            if hasattr(self.client, "query_points"):
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    using="dense",
                    query_filter=filter_conditions,
                    limit=limit,
                    with_payload=True
                ).points
                return [
                    {
                        "point_id": str(r.id),
                        "score": float(r.score) if hasattr(r, "score") else 1.0,
                        "payload": r.payload or {}
                    }
                    for r in results
                ]
            elif hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=("dense", query_vector),
                    query_filter=filter_conditions,
                    limit=limit,
                    with_payload=True
                )
                return [
                    {
                        "point_id": str(r.id),
                        "score": float(r.score),
                        "payload": r.payload or {}
                    }
                    for r in results
                ]
            return []
        except Exception as e:
            logger.warning(f"Qdrant dense search fallback/error: {e}")
            return []

    def search_sparse(
        self,
        sparse_query: Dict[int, float],
        user_id: str,
        knowledge_base_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Perform sparse BM25 vector search with payload filtering."""
        if not sparse_query:
            return []

        filter_conditions = models.Filter(
            must=[
                models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id))),
                models.FieldCondition(key="knowledge_base_id", match=models.MatchValue(value=str(knowledge_base_id))),
            ]
        )

        indices = list(sparse_query.keys())
        values = list(sparse_query.values())

        try:
            if hasattr(self.client, "query_points"):
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=models.SparseVector(indices=indices, values=values),
                    using="bm25",
                    query_filter=filter_conditions,
                    limit=limit,
                    with_payload=True
                ).points
                return [
                    {
                        "point_id": str(r.id),
                        "score": float(r.score) if hasattr(r, "score") else 1.0,
                        "payload": r.payload or {}
                    }
                    for r in results
                ]
            elif hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=models.NamedSparseVector(
                        name="bm25",
                        vector=models.SparseVector(indices=indices, values=values)
                    ),
                    query_filter=filter_conditions,
                    limit=limit,
                    with_payload=True
                )
                return [
                    {
                        "point_id": str(r.id),
                        "score": float(r.score),
                        "payload": r.payload or {}
                    }
                    for r in results
                ]
            return []
        except Exception as e:
            logger.warning(f"Qdrant sparse search fallback/error: {e}")
            return []

    def delete_by_document(self, document_id: str) -> bool:
        """Delete all points belonging to a specific document."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id)))
                        ]
                    )
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete points for doc {document_id}: {e}")
            return False


qdrant_store = QdrantStore()
