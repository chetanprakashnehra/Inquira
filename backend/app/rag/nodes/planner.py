import logging
import re
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from app.rag.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)


class QueryPlannerNode:
    """Stage 1: Intent detection, conversation coreference resolution, and HyDE expansion."""

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.FAST_LLM_MODEL
        self._llm = None

    def _get_llm(self):
        if self._llm is None and self.api_key and self.api_key.startswith("sk-"):
            self._llm = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                temperature=0.0
            )
        return self._llm

    def plan_and_expand(self, state: AgentState) -> Dict[str, Any]:
        query = state.get("query", "")
        history = state.get("chat_history", [])
        llm = self._get_llm()

        # Default fallback values
        intent = "rag"
        rewritten_query = query
        hyde_doc = query

        # 1. Intent Detection for greeting / conversational vs knowledge search
        cleaned_q = re.sub(r"[^\w\s]", "", query.lower()).strip()
        greeting_patterns = [
            "hi", "hello", "hey", "good morning", "good evening", "good afternoon",
            "how are you", "who are you", "what is inquira", "hello how are you",
            "hi there", "hello there", "help"
        ]
        
        is_greeting = cleaned_q in greeting_patterns or any(
            cleaned_q.startswith(g) for g in ["hi ", "hello ", "hey "]
        ) and len(cleaned_q.split()) <= 6

        if is_greeting:
            return {
                "intent": "direct",
                "rewritten_query": query,
                "hyde_document": None
            }

        if llm:
            try:
                # 2. Query Rewriting with Conversation History Coreference Resolution
                history_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history[-6:]]) if history else "None"
                
                planning_prompt = f"""You are a Query Planner for an Agentic RAG system.
Given the Conversation History and the Latest User Query, perform two tasks:
1. Coreference Resolution: Rewrite the user's latest query so it is self-contained, resolving pronouns or references to previous context.
2. HyDE Generation: Write a concise (2-4 sentences) hypothetical passage that directly answers the question as it might appear in a factual document.

Conversation History:
{history_text}

Latest User Query: "{query}"

Output in exact format:
REWRITTEN_QUERY: <standalone query>
HYDE_DOC: <hypothetical document passage>
"""
                response = llm.invoke([HumanMessage(content=planning_prompt)]).content
                
                if "REWRITTEN_QUERY:" in response and "HYDE_DOC:" in response:
                    parts = response.split("HYDE_DOC:")
                    rewritten = parts[0].replace("REWRITTEN_QUERY:", "").strip()
                    hyde = parts[1].strip()
                    if rewritten:
                        rewritten_query = rewritten
                    if hyde:
                        hyde_doc = hyde
            except Exception as e:
                logger.warning(f"LLM Query Planning error ({e}), using raw query fallback.")

        return {
            "intent": intent,
            "rewritten_query": rewritten_query,
            "hyde_document": hyde_doc
        }


planner_node = QueryPlannerNode()
