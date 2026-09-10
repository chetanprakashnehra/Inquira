"""
Comprehensive end-to-end integration tests for Inquira.

Tests the full lifecycle:
  1. Document parsing, chunking, and embedding
  2. Qdrant vector upsert and search
  3. RRF fusion and re-ranking
  4. LangGraph agentic workflow execution
  5. API endpoints (auth, KB, documents, chat)
"""

import os
import uuid
import pytest
from httpx import AsyncClient

from app.services.parser import DocumentParser, ParsedPage
from app.services.chunker import DocumentChunker
from app.services.embedding import EmbeddingService
from app.rag.retrieval.qdrant_client import QdrantStore
from app.rag.retrieval.rrf import ReciprocalRankFusion
from app.rag.retrieval.reranker import CrossEncoderReranker
from app.rag.nodes.planner import QueryPlannerNode
from app.rag.graph import rag_graph

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# =====================================================================
# 1. Document Parsing Tests
# =====================================================================

class TestDocumentParser:
    def test_parse_txt_file(self):
        """Parse a real .txt file and verify pages are extracted."""
        path = os.path.join(FIXTURES_DIR, "sample_architecture.txt")
        pages = DocumentParser.parse_file(path, "txt")
        assert len(pages) >= 1
        assert pages[0].page_number == 1
        assert "Inquira" in pages[0].text
        assert "hybrid retrieval" in pages[0].text.lower()

    def test_parse_markdown_file(self):
        """Parse a real .md file and verify content extraction."""
        path = os.path.join(FIXTURES_DIR, "sample_benchmarks.md")
        pages = DocumentParser.parse_file(path, "md")
        assert len(pages) >= 1
        assert "Precision@5" in pages[0].text
        assert "RAGAS" in pages[0].text

    def test_parse_nonexistent_file_raises(self):
        """Attempting to parse a missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            DocumentParser.parse_file("/no/such/file.txt", "txt")

    def test_clean_text_removes_excess_blank_lines(self):
        """Verify text cleaning normalizes whitespace."""
        dirty = "Hello\n\n\n\n\nWorld\n\n\nTest"
        cleaned = DocumentParser._clean_text(dirty)
        # No more than one consecutive blank line
        assert "\n\n\n" not in cleaned
        assert "Hello" in cleaned
        assert "World" in cleaned


# =====================================================================
# 2. Document Chunking Tests
# =====================================================================

class TestDocumentChunker:
    def test_chunking_real_document(self):
        """Chunk the sample architecture document and verify metadata."""
        path = os.path.join(FIXTURES_DIR, "sample_architecture.txt")
        pages = DocumentParser.parse_file(path, "txt")
        chunker = DocumentChunker(chunk_size=300, chunk_overlap=50)
        chunks = chunker.chunk_pages(pages)

        assert len(chunks) >= 3, f"Expected at least 3 chunks, got {len(chunks)}"

        # Verify monotonically increasing chunk indices
        for i, c in enumerate(chunks):
            assert c.chunk_index == i, f"Chunk index mismatch at position {i}"

        # All chunks should have page_number = 1 (single-page txt file)
        assert all(c.page_number == 1 for c in chunks)

        # Verify token counts are positive
        assert all(c.token_count > 0 for c in chunks)

        # Verify no chunk is empty
        assert all(len(c.content.strip()) > 0 for c in chunks)

    def test_chunking_preserves_content(self):
        """Verify key phrases survive the chunking process."""
        path = os.path.join(FIXTURES_DIR, "sample_architecture.txt")
        pages = DocumentParser.parse_file(path, "txt")
        chunker = DocumentChunker(chunk_size=500, chunk_overlap=100)
        chunks = chunker.chunk_pages(pages)

        all_text = " ".join(c.content for c in chunks)
        assert "RRF" in all_text or "Reciprocal Rank Fusion" in all_text
        assert "Cross-Encoder" in all_text
        assert "HyDE" in all_text
        assert "Qdrant" in all_text

    def test_empty_page_produces_no_chunks(self):
        """Verify empty pages don't generate chunks."""
        pages = [ParsedPage(page_number=1, text="   \n\n   ")]
        chunker = DocumentChunker()
        chunks = chunker.chunk_pages(pages)
        assert len(chunks) == 0


# =====================================================================
# 3. Embedding Service Tests
# =====================================================================

class TestEmbeddingService:
    def test_dense_embedding_dimensions(self):
        """Verify dense embeddings produce vectors of the correct dimension."""
        svc = EmbeddingService()
        texts = ["What is hybrid retrieval?", "Explain RRF fusion."]
        embeddings = svc.get_dense_embeddings(texts)
        assert len(embeddings) == 2
        # All vectors should be the same length
        dim = len(embeddings[0])
        assert dim > 0
        assert all(len(e) == dim for e in embeddings)

    def test_sparse_embedding_structure(self):
        """Verify sparse embeddings produce valid dict structures."""
        svc = EmbeddingService()
        texts = ["What is BM25 lexical search?"]
        sparse = svc.get_sparse_embeddings(texts)
        assert len(sparse) == 1
        assert isinstance(sparse[0], dict)
        assert len(sparse[0]) > 0
        # All keys should be ints, all values should be floats
        for k, v in sparse[0].items():
            assert isinstance(k, int)
            assert isinstance(v, float)

    def test_empty_input_returns_empty(self):
        """Empty input should return empty output."""
        svc = EmbeddingService()
        assert svc.get_dense_embeddings([]) == []
        assert svc.get_sparse_embeddings([]) == []

    def test_query_embedding_single(self):
        """Verify single query embedding helper works."""
        svc = EmbeddingService()
        vec = svc.get_query_dense_embedding("test query")
        assert isinstance(vec, list)
        assert len(vec) > 0


# =====================================================================
# 4. Qdrant Vector Store Tests
# =====================================================================

class TestQdrantStore:
    def setup_method(self):
        """Create a fresh in-memory Qdrant store for each test."""
        from qdrant_client import QdrantClient, models
        self.store = QdrantStore.__new__(QdrantStore)
        self.store.collection_name = f"test_{uuid.uuid4().hex[:8]}"
        self.store.dense_dim = 8  # small dim for fast tests
        self.store.client = QdrantClient(":memory:")
        self.store._ensure_collection()

    def test_upsert_and_search_dense(self):
        """Upsert chunks and verify dense search retrieves them."""
        user_id = "user-001"
        kb_id = "kb-001"

        point_ids = [str(uuid.uuid4()) for _ in range(3)]
        dense_vectors = [
            [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        ]
        sparse_vectors = [{1: 0.5, 2: 0.3}, {3: 0.8}, {1: 0.2, 4: 0.6}]
        payloads = [
            {"user_id": user_id, "knowledge_base_id": kb_id, "document_id": "doc-1", "content": "HyDE generates hypothetical answers", "file_name": "arch.txt", "page_number": 1, "chunk_index": 0},
            {"user_id": user_id, "knowledge_base_id": kb_id, "document_id": "doc-1", "content": "BM25 handles exact keyword matching", "file_name": "arch.txt", "page_number": 1, "chunk_index": 1},
            {"user_id": user_id, "knowledge_base_id": kb_id, "document_id": "doc-1", "content": "RRF fuses dense and sparse results", "file_name": "arch.txt", "page_number": 1, "chunk_index": 2},
        ]

        result = self.store.upsert_chunks(point_ids, dense_vectors, sparse_vectors, payloads)
        assert result is True

        # Search dense
        results = self.store.search_dense(
            query_vector=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            user_id=user_id,
            knowledge_base_id=kb_id,
            limit=3
        )
        assert len(results) == 3
        # The most similar vector should be the first one we inserted
        assert "HyDE" in results[0]["payload"]["content"]

    def test_search_with_wrong_user_returns_empty(self):
        """Verify tenant isolation: wrong user_id yields no results."""
        user_id = "user-001"
        kb_id = "kb-001"

        self.store.upsert_chunks(
            [str(uuid.uuid4())],
            [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]],
            [{1: 0.5}],
            [{"user_id": user_id, "knowledge_base_id": kb_id, "document_id": "d1", "content": "test"}]
        )

        results = self.store.search_dense(
            query_vector=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            user_id="wrong-user",
            knowledge_base_id=kb_id,
            limit=10
        )
        assert len(results) == 0

    def test_delete_by_document(self):
        """Verify deletion removes all points for a given document."""
        user_id = "user-001"
        kb_id = "kb-001"
        doc_id = "doc-to-delete"

        self.store.upsert_chunks(
            [str(uuid.uuid4()), str(uuid.uuid4())],
            [[0.1]*8, [0.2]*8],
            [{1: 0.5}, {2: 0.3}],
            [
                {"user_id": user_id, "knowledge_base_id": kb_id, "document_id": doc_id, "content": "chunk A"},
                {"user_id": user_id, "knowledge_base_id": kb_id, "document_id": doc_id, "content": "chunk B"},
            ]
        )

        # Verify they exist
        results_before = self.store.search_dense([0.1]*8, user_id, kb_id, limit=10)
        assert len(results_before) == 2

        # Delete
        self.store.delete_by_document(doc_id)

        # Verify they're gone
        results_after = self.store.search_dense([0.1]*8, user_id, kb_id, limit=10)
        assert len(results_after) == 0


# =====================================================================
# 5. RRF Fusion Tests
# =====================================================================

class TestRRFFusion:
    def test_rrf_merges_overlapping_lists(self):
        """Two lists sharing some docs should boost shared items."""
        list1 = [
            {"point_id": "A", "payload": {"content": "A"}},
            {"point_id": "B", "payload": {"content": "B"}},
            {"point_id": "C", "payload": {"content": "C"}},
        ]
        list2 = [
            {"point_id": "B", "payload": {"content": "B"}},
            {"point_id": "D", "payload": {"content": "D"}},
            {"point_id": "A", "payload": {"content": "A"}},
        ]
        fused = ReciprocalRankFusion.fuse([list1, list2], k=60, top_n=10)

        # A and B appear in both lists, so they should be top-ranked
        top_ids = [f["point_id"] for f in fused[:2]]
        assert "A" in top_ids or "B" in top_ids
        assert len(fused) == 4  # A, B, C, D

    def test_rrf_single_list_preserves_order(self):
        """Single ranked list should preserve original ordering."""
        single = [
            {"point_id": "X", "payload": {}},
            {"point_id": "Y", "payload": {}},
            {"point_id": "Z", "payload": {}},
        ]
        fused = ReciprocalRankFusion.fuse([single], k=60, top_n=3)
        assert [f["point_id"] for f in fused] == ["X", "Y", "Z"]

    def test_rrf_respects_top_n_limit(self):
        """RRF should return at most top_n results."""
        big_list = [{"point_id": f"doc-{i}", "payload": {}} for i in range(20)]
        fused = ReciprocalRankFusion.fuse([big_list], k=60, top_n=5)
        assert len(fused) == 5


# =====================================================================
# 6. Re-Ranker Tests
# =====================================================================

class TestCrossEncoderReranker:
    def test_reranker_returns_top_k(self):
        """Reranker should return at most top_k items."""
        reranker = CrossEncoderReranker()
        candidates = [
            {"point_id": f"c{i}", "payload": {"content": f"Chunk content about topic {i}"}, "rrf_score": 0.1 - i*0.01}
            for i in range(10)
        ]
        results = reranker.rerank("What is the main topic?", candidates, top_k=3)
        assert len(results) <= 3
        assert all("rerank_score" in r for r in results)

    def test_reranker_empty_candidates(self):
        """Reranker with no candidates should return empty list."""
        reranker = CrossEncoderReranker()
        results = reranker.rerank("test query", [], top_k=5)
        assert results == []


# =====================================================================
# 7. Query Planner Tests
# =====================================================================

class TestQueryPlanner:
    def test_greeting_detected_as_direct(self):
        """Greetings should route to direct intent."""
        planner = QueryPlannerNode()
        for greeting in ["Hello", "Hi", "Hey", "hello there", "good morning"]:
            result = planner.plan_and_expand({
                "query": greeting, "chat_history": [],
                "knowledge_base_id": "kb1", "user_id": "u1"
            })
            assert result["intent"] == "direct", f"'{greeting}' was not classified as direct"

    def test_knowledge_query_detected_as_rag(self):
        """Knowledge-seeking questions should route to RAG intent."""
        planner = QueryPlannerNode()
        result = planner.plan_and_expand({
            "query": "What are the 5 techniques in the hybrid retrieval pipeline?",
            "chat_history": [],
            "knowledge_base_id": "kb1", "user_id": "u1"
        })
        assert result["intent"] == "rag"
        assert len(result["rewritten_query"]) > 0


# =====================================================================
# 8. Full LangGraph Workflow Tests
# =====================================================================

class TestLangGraphWorkflow:
    @pytest.mark.asyncio
    async def test_direct_greeting_flow(self):
        """Conversational greeting should produce a direct response."""
        state = {
            "query": "Hello!",
            "knowledge_base_id": "00000000-0000-0000-0000-000000000001",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "chat_history": [],
            "intent": "", "rewritten_query": "", "hyde_document": None,
            "retrieved_dense": [], "retrieved_sparse": [],
            "fused_candidates": [], "ranked_chunks": [],
            "generated_response": "", "citations": [],
            "verification_score": 0.0, "is_verified": False,
            "retry_count": 0, "final_output": ""
        }
        result = await rag_graph.ainvoke(state)
        assert result["intent"] == "direct"
        assert len(result["final_output"]) > 0
        assert result["is_verified"] is True

    @pytest.mark.asyncio
    async def test_rag_flow_with_no_documents(self):
        """RAG query with empty KB should return informative no-results message."""
        state = {
            "query": "What is the RRF formula?",
            "knowledge_base_id": "empty-kb",
            "user_id": "user-no-docs",
            "chat_history": [],
            "intent": "", "rewritten_query": "", "hyde_document": None,
            "retrieved_dense": [], "retrieved_sparse": [],
            "fused_candidates": [], "ranked_chunks": [],
            "generated_response": "", "citations": [],
            "verification_score": 0.0, "is_verified": False,
            "retry_count": 0, "final_output": ""
        }
        result = await rag_graph.ainvoke(state)
        assert result["intent"] == "rag"
        assert result["is_verified"] is True
        assert len(result["final_output"]) > 0


# =====================================================================
# 9. Full Pipeline Integration Test (Parse → Chunk → Embed → Index → Retrieve)
# =====================================================================

class TestFullPipelineIntegration:
    def test_end_to_end_retrieval(self):
        """
        Full pipeline: parse a real document, chunk it, embed chunks,
        upsert into Qdrant, then search and verify relevant chunks are returned.
        """
        from qdrant_client import QdrantClient

        # 1. Parse
        path = os.path.join(FIXTURES_DIR, "sample_architecture.txt")
        pages = DocumentParser.parse_file(path, "txt")
        assert len(pages) >= 1

        # 2. Chunk
        chunker = DocumentChunker(chunk_size=400, chunk_overlap=50)
        chunks = chunker.chunk_pages(pages)
        assert len(chunks) >= 3

        # 3. Embed
        svc = EmbeddingService()
        texts = [c.content for c in chunks]
        dense_vecs = svc.get_dense_embeddings(texts)
        sparse_vecs = svc.get_sparse_embeddings(texts)
        assert len(dense_vecs) == len(chunks)
        assert len(sparse_vecs) == len(chunks)

        # 4. Create a fresh in-memory Qdrant store
        store = QdrantStore.__new__(QdrantStore)
        store.collection_name = f"integration_{uuid.uuid4().hex[:8]}"
        store.dense_dim = len(dense_vecs[0])
        store.client = QdrantClient(":memory:")
        store._ensure_collection()

        user_id = "integration-user"
        kb_id = "integration-kb"
        doc_id = "integration-doc"

        point_ids = [str(uuid.uuid4()) for _ in chunks]
        payloads = [
            {
                "user_id": user_id,
                "knowledge_base_id": kb_id,
                "document_id": doc_id,
                "file_name": "sample_architecture.txt",
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "content": c.content
            }
            for c in chunks
        ]

        store.upsert_chunks(point_ids, dense_vecs, sparse_vecs, payloads)

        # 5. Search: query about RRF should return relevant chunks
        query = "What is Reciprocal Rank Fusion and what smoothing constant k is used?"
        q_dense = svc.get_query_dense_embedding(query)
        q_sparse = svc.get_query_sparse_embedding(query)

        dense_results = store.search_dense(q_dense, user_id, kb_id, limit=10)
        sparse_results = store.search_sparse(q_sparse, user_id, kb_id, limit=10)

        # At least one search method should return results
        total_results = len(dense_results) + len(sparse_results)
        assert total_results > 0, "No results returned from either dense or sparse search"

        # 6. Fuse with RRF
        if dense_results or sparse_results:
            fused = ReciprocalRankFusion.fuse(
                [dense_results, sparse_results], k=60, top_n=5
            )
            assert len(fused) > 0

            # Verify at least one result mentions RRF or rank fusion
            all_content = " ".join(r["payload"].get("content", "") for r in fused)
            assert "RRF" in all_content or "Reciprocal" in all_content or "rank" in all_content.lower(), \
                f"Expected RRF-related content in top results. Got: {all_content[:200]}"

    def test_document_deletion_cleans_vectors(self):
        """Verify that deleting a document removes all its vectors from Qdrant."""
        from qdrant_client import QdrantClient

        store = QdrantStore.__new__(QdrantStore)
        store.collection_name = f"del_test_{uuid.uuid4().hex[:8]}"
        store.dense_dim = 4
        store.client = QdrantClient(":memory:")
        store._ensure_collection()

        user_id = "u1"
        kb_id = "kb1"
        doc_id = "doc-to-delete"

        # Insert 3 chunks for the document
        store.upsert_chunks(
            [str(uuid.uuid4()) for _ in range(3)],
            [[0.1, 0.2, 0.3, 0.4]] * 3,
            [{1: 0.5}] * 3,
            [{"user_id": user_id, "knowledge_base_id": kb_id, "document_id": doc_id, "content": f"chunk {i}"} for i in range(3)]
        )

        # Verify insertion
        before = store.search_dense([0.1, 0.2, 0.3, 0.4], user_id, kb_id, limit=10)
        assert len(before) == 3

        # Delete
        store.delete_by_document(doc_id)

        # Verify deletion
        after = store.search_dense([0.1, 0.2, 0.3, 0.4], user_id, kb_id, limit=10)
        assert len(after) == 0


# =====================================================================
# 10. API Endpoint Integration Tests
# =====================================================================

class TestAPIEndpoints:
    """Tests that exercise the actual HTTP endpoints end-to-end."""

    @staticmethod
    async def _register_and_login(client: AsyncClient) -> dict:
        """Helper: register a user and return auth headers."""
        email = f"test_{uuid.uuid4().hex[:6]}@inquira.ai"
        await client.post("/api/v1/auth/register", json={
            "email": email, "password": "TestPass123!", "full_name": "Test User"
        })
        login_res = await client.post("/api/v1/auth/login/json", json={
            "email": email, "password": "TestPass123!"
        })
        token = login_res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_full_kb_and_document_lifecycle(self, client: AsyncClient, monkeypatch):
        """Test: register → create KB → upload doc → list docs → delete doc → delete KB."""
        from unittest.mock import MagicMock
        import app.api.v1.documents as doc_module

        # Mock process_document.delay to be a no-op (avoid Celery/background task hang)
        mock_task = MagicMock()
        monkeypatch.setattr(doc_module, "process_document", mock_task)

        # Mock delete_document_task to be a no-op
        mock_delete_task = MagicMock()
        monkeypatch.setattr(doc_module, "delete_document_task", mock_delete_task)

        headers = await self._register_and_login(client)

        # 1. Create Knowledge Base
        kb_res = await client.post("/api/v1/knowledge-bases", headers=headers, json={
            "name": "Integration Test KB", "description": "Testing full lifecycle"
        })
        assert kb_res.status_code == 201
        kb_id = kb_res.json()["id"]

        # 2. List KBs
        list_res = await client.get("/api/v1/knowledge-bases", headers=headers)
        assert list_res.status_code == 200
        assert any(kb["id"] == kb_id for kb in list_res.json())

        # 3. Upload a document (Celery dispatch is mocked)
        fixture_path = os.path.join(FIXTURES_DIR, "sample_architecture.txt")
        with open(fixture_path, "rb") as f:
            upload_res = await client.post(
                "/api/v1/documents/upload",
                headers=headers,
                data={"knowledge_base_id": kb_id},
                files={"files": ("sample_architecture.txt", f, "text/plain")}
            )
        assert upload_res.status_code == 202
        docs = upload_res.json()["documents"]
        assert len(docs) == 1
        doc_id = docs[0]["id"]
        assert docs[0]["status"] == "PENDING"

        # Verify Celery task was dispatched
        mock_task.delay.assert_called_once()

        # 4. List documents
        doc_list_res = await client.get(
            f"/api/v1/documents?knowledge_base_id={kb_id}", headers=headers
        )
        assert doc_list_res.status_code == 200
        assert len(doc_list_res.json()) >= 1

        # 5. Get single document
        doc_get_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert doc_get_res.status_code == 200
        assert doc_get_res.json()["file_name"] == "sample_architecture.txt"

        # 6. Delete document
        del_res = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
        assert del_res.status_code == 202

        # 7. Delete KB
        del_kb_res = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=headers)
        assert del_kb_res.status_code == 204

    @pytest.mark.asyncio
    async def test_unauthorized_access_rejected(self, client: AsyncClient):
        """Endpoints should reject requests without valid auth."""
        res = await client.get("/api/v1/knowledge-bases")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should be accessible without auth."""
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"
