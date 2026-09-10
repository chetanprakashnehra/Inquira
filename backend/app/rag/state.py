from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict


class MessageItem(TypedDict):
    role: str
    content: str


class CitationItem(TypedDict):
    document_id: Optional[str]
    document_name: str
    page_number: Optional[int]
    chunk_index: int
    content: str
    relevance_score: Optional[float]


class AgentState(TypedDict):
    # Input parameters
    query: str
    knowledge_base_id: str
    user_id: str
    chat_history: List[MessageItem]

    # Stage 1: Planning & Expansion
    intent: str  # "rag", "direct", "clarify"
    rewritten_query: str
    hyde_document: Optional[str]

    # Stage 2: Hybrid Retrieval & Re-ranking
    retrieved_dense: List[Dict[str, Any]]
    retrieved_sparse: List[Dict[str, Any]]
    fused_candidates: List[Dict[str, Any]]
    ranked_chunks: List[Dict[str, Any]]

    # Stage 3: Generation & Citation Verification
    generated_response: str
    citations: List[CitationItem]
    verification_score: float
    is_verified: bool
    retry_count: int
    final_output: str
