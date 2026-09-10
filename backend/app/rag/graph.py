import logging
from langgraph.graph import StateGraph, END
from app.rag.state import AgentState
from app.rag.nodes.planner import planner_node
from app.rag.nodes.retriever import retriever_node
from app.rag.nodes.verifier import verifier_node

logger = logging.getLogger(__name__)


def route_after_planner(state: AgentState) -> str:
    """Conditional branching based on user intent."""
    intent = state.get("intent", "rag")
    if intent == "direct":
        return "direct_generator"
    return "retriever"


def route_after_verifier(state: AgentState) -> str:
    """Conditional branching based on citation verification score and retry count."""
    is_verified = state.get("is_verified", True)
    retry_count = state.get("retry_count", 0)

    if not is_verified and retry_count <= 1:
        return "retriever"
    return END


def build_rag_graph():
    """Build and compile the 3-Stage LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # 1. Add Nodes
    workflow.add_node("planner", planner_node.plan_and_expand)
    workflow.add_node("direct_generator", verifier_node.generate_direct)
    workflow.add_node("retriever", retriever_node.retrieve)
    workflow.add_node("grounded_generator", verifier_node.generate_grounded)
    workflow.add_node("verifier", verifier_node.verify_citations)

    # 2. Set Entry Point
    workflow.set_entry_point("planner")

    # 3. Add Edges & Conditional Edges
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "direct_generator": "direct_generator",
            "retriever": "retriever"
        }
    )

    workflow.add_edge("direct_generator", END)
    workflow.add_edge("retriever", "grounded_generator")
    workflow.add_edge("grounded_generator", "verifier")

    workflow.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "retriever": "retriever",
            END: END
        }
    )

    # 4. Compile Graph
    compiled_graph = workflow.compile()
    logger.info("LangGraph Agentic RAG workflow successfully compiled.")
    return compiled_graph


rag_graph = build_rag_graph()
