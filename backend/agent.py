import asyncio
import sys
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from database import SessionLocal
from retrieval import retrieve_documents
from rag import generate_answer, verify_answer


# ============================================================
# STATE
# ============================================================

class RAGState(TypedDict):
    question: str
    knowledge_base_id: str
    history: list[dict]
    contexts: list[dict]
    answer: str
    citations: list[dict]
    is_supported: bool
    retry_count: int


# ============================================================
# RETRIEVAL
# ============================================================

async def retrieve(state: RAGState):

    print("\n[RETRIEVE]")

    async with SessionLocal() as db:

        contexts = await retrieve_documents(
            question=state["question"],
            knowledge_base_id=state["knowledge_base_id"],
            db=db,
            dense_limit=10,
            bm25_limit=10,
            final_limit=5,
        )

    print(f"Retrieved {len(contexts)} chunks")

    return {
        "contexts": contexts
    }


# ============================================================
# GENERATION
# ============================================================

def generate(state: RAGState):

    print("\n[GENERATE]")

    result = generate_answer(
        question=state["question"],
        contexts=state["contexts"],
        history=state["history"],
    )

    return {
        "answer": result["answer"],
        "citations": result["citations"],
    }


# ============================================================
# VERIFICATION
# ============================================================

def verify(state: RAGState):

    print("\n[VERIFY]")

    supported = verify_answer(
        question=state["question"],
        answer=state["answer"],
        contexts=state["contexts"],
    )

    print("Supported:", supported)

    return {
        "is_supported": supported
    }


# ============================================================
# DECISION
# ============================================================

def check_verification(state: RAGState):

    if state["is_supported"]:

        print("\n[DECISION] Answer supported")

        return "end"

    if state["retry_count"] >= 2:

        print("\n[DECISION] Maximum retries reached")

        return "end"

    print("\n[DECISION] Answer not supported")

    return "retry"


# ============================================================
# RETRY
# ============================================================

def increment_retry(state: RAGState):

    new_count = state["retry_count"] + 1

    print(f"\n[RETRY] Attempt {new_count}")

    return {
        "retry_count": new_count
    }


# ============================================================
# BUILD GRAPH
# ============================================================

graph_builder = StateGraph(RAGState)

graph_builder.add_node(
    "retrieve",
    retrieve
)

graph_builder.add_node(
    "generate",
    generate
)

graph_builder.add_node(
    "verify",
    verify
)

graph_builder.add_node(
    "increment_retry",
    increment_retry
)


# ============================================================
# GRAPH FLOW
# ============================================================

graph_builder.add_edge(
    START,
    "retrieve"
)

graph_builder.add_edge(
    "retrieve",
    "generate"
)

graph_builder.add_edge(
    "generate",
    "verify"
)

graph_builder.add_conditional_edges(
    "verify",
    check_verification,
    {
        "end": END,
        "retry": "increment_retry",
    },
)

graph_builder.add_edge(
    "increment_retry",
    "retrieve"
)


graph = graph_builder.compile()


# ============================================================
# PUBLIC AGENT FUNCTION
# ============================================================

async def run_agent(
    question: str,
    knowledge_base_id: str,
    history: list[dict] | None = None,
):

    initial_state: RAGState = {

        "question": question,

        "knowledge_base_id": knowledge_base_id,

        "history": history or [],

        "contexts": [],

        "answer": "",

        "citations": [],

        "is_supported": False,

        "retry_count": 0,
    }

    result = await graph.ainvoke(
        initial_state
    )

    return result

# ============================================================
# STREAMING AGENT WITH START / COMPLETION EVENTS
# ============================================================

async def stream_agent(
    question: str,
    knowledge_base_id: str,
    history: list[dict] | None = None,
):
    initial_state: RAGState = {
        "question": question,
        "knowledge_base_id": knowledge_base_id,
        "history": history or [],
        "contexts": [],
        "answer": "",
        "citations": [],
        "is_supported": False,
        "retry_count": 0,
    }

    final_state = dict(initial_state)

    stages = {
        "retrieve": "Retrieving relevant documents",
        "generate": "Generating answer",
        "verify": "Verifying answer",
        "increment_retry": "Retrying answer generation",
    }

    async for event in graph.astream_events(
        initial_state,
        version="v2",
    ):
        event_type = event.get("event")
        node_name = event.get("metadata", {}).get(
            "langgraph_node"
        )

        # Ignore events that don't belong to our graph nodes.
        if node_name not in stages:
            continue

        # Avoid reporting nested model/tool events as separate
        # starts or completions for the same graph node.
        if event.get("name") != node_name:
            continue

        if event_type == "on_chain_start":
            yield {
                "type": "progress",
                "status": "started",
                "node": node_name,
                "message": stages[node_name],
                "retry_count": final_state["retry_count"],
            }

        elif event_type == "on_chain_end":
            output = event.get("data", {}).get("output")

            if isinstance(output, dict):
                final_state.update(output)

            yield {
                "type": "progress",
                "status": "completed",
                "node": node_name,
                "message": stages[node_name],
                "retry_count": final_state["retry_count"],
            }

    # Send the final result only after the graph completes.
    yield {
        "type": "result",
        "answer": final_state["answer"],
        "citations": final_state["citations"],
        "is_supported": final_state["is_supported"],
        "retry_count": final_state["retry_count"],
    }


# ============================================================
# STANDALONE TEST
# ============================================================

async def main():

    knowledge_base_id = "YOUR_KNOWLEDGE_BASE_ID"

    initial_state: RAGState = {

        "question": "What is Inquira?",

        "knowledge_base_id": knowledge_base_id,

        "history": [],

        "contexts": [],

        "answer": "",

        "citations": [],

        "is_supported": False,

        "retry_count": 0,
    }

    result = await graph.ainvoke(
        initial_state
    )

    print("\n" + "=" * 60)
    print("FINAL ANSWER")
    print("=" * 60)

    print(result["answer"])

    print("\n" + "=" * 60)
    print("CITATIONS")
    print("=" * 60)

    for citation in result["citations"]:
        print(citation)

    print("\n" + "=" * 60)
    print("SUPPORTED")
    print("=" * 60)

    print(result["is_supported"])

    print("\n" + "=" * 60)
    print("RETRY COUNT")
    print("=" * 60)

    print(result["retry_count"])


# ============================================================
# RUN DIRECTLY
# ============================================================

if __name__ == "__main__":

    if sys.platform == "win32":

        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())