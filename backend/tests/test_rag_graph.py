import pytest
from app.rag.graph import rag_graph
from app.rag.nodes.verifier import verifier_node


@pytest.mark.asyncio
async def test_langgraph_direct_greeting_flow():
    """Verify conversational queries route through direct generator without error."""
    state = {
        "query": "Hello, how are you?",
        "knowledge_base_id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "chat_history": [],
        "intent": "",
        "rewritten_query": "",
        "hyde_document": None,
        "retrieved_dense": [],
        "retrieved_sparse": [],
        "fused_candidates": [],
        "ranked_chunks": [],
        "generated_response": "",
        "citations": [],
        "verification_score": 0.0,
        "is_verified": False,
        "retry_count": 0,
        "final_output": ""
    }
    result = await rag_graph.ainvoke(state)
    assert result["intent"] == "direct"
    assert len(result["final_output"]) > 0
    assert result["is_verified"] is True


def test_citation_extraction_from_ranked_chunks():
    """Verify citation parser correctly matches chunks with metadata."""
    ranked_chunks = [
        {
            "payload": {
                "file_name": "architecture.pdf",
                "page_number": 3,
                "chunk_index": 5,
                "content": "Inquira utilizes a 5-technique hybrid retrieval engine.",
                "document_id": "11111111-1111-1111-1111-111111111111"
            },
            "rerank_score": 0.92
        }
    ]
    text = "Inquira uses hybrid retrieval [Doc: architecture.pdf, Page: 3, Chunk: 5]."
    citations = verifier_node._extract_citations(text, ranked_chunks)
    
    assert len(citations) == 1
    assert citations[0]["document_name"] == "architecture.pdf"
    assert citations[0]["page_number"] == 3
    assert citations[0]["chunk_index"] == 5
