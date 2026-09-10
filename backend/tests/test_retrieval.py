import pytest
from app.rag.retrieval.rrf import ReciprocalRankFusion
from app.services.chunker import DocumentChunker
from app.services.parser import ParsedPage


def test_rrf_scoring_deterministic():
    """Verify Reciprocal Rank Fusion mathematical calculation."""
    # List 1 (Dense): docA (rank 1), docB (rank 2), docC (rank 3)
    list1 = [
        {"point_id": "docA", "payload": {"content": "Text A"}},
        {"point_id": "docB", "payload": {"content": "Text B"}},
        {"point_id": "docC", "payload": {"content": "Text C"}},
    ]
    # List 2 (Sparse): docB (rank 1), docA (rank 2), docD (rank 3)
    list2 = [
        {"point_id": "docB", "payload": {"content": "Text B"}},
        {"point_id": "docA", "payload": {"content": "Text A"}},
        {"point_id": "docD", "payload": {"content": "Text D"}},
    ]

    fused = ReciprocalRankFusion.fuse([list1, list2], k=60, top_n=10)

    # docA score: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.0163934 + 0.0161290 = 0.0325224
    # docB score: 1/(60+2) + 1/(60+1) = 0.0325224
    # Both docA and docB tie for top spots and are significantly higher than docC / docD
    assert len(fused) == 4
    top_two_ids = {fused[0]["point_id"], fused[1]["point_id"]}
    assert top_two_ids == {"docA", "docB"}
    assert fused[0]["rrf_score"] > fused[2]["rrf_score"]


def test_document_chunking_with_page_attribution():
    """Verify chunker retains page numbering and sequential indexing."""
    pages = [
        ParsedPage(page_number=1, text="This is page one content. " * 30),
        ParsedPage(page_number=2, text="This is page two content. " * 30),
    ]
    chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk_pages(pages)

    assert len(chunks) >= 2
    # Ensure chunk_index increments monotonically starting from 0
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
    # Page numbers are correctly assigned
    page_numbers = {c.page_number for c in chunks}
    assert page_numbers == {1, 2}
