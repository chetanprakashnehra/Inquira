from groq import Groq

from config import settings


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=settings.groq_api_key
)


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(
    question: str,
    contexts: list[dict],
    history: list[dict] | None = None,
) -> dict:

    # --------------------------------------------------------
    # Build document context
    # --------------------------------------------------------

    context_parts = []

    for index, item in enumerate(
        contexts,
        start=1
    ):

        context_parts.append(
            f"[{index}] {item['content']}"
        )

    context_text = "\n\n".join(
        context_parts
    )

    # --------------------------------------------------------
    # Build conversation history
    # --------------------------------------------------------

    history_text = ""

    if history:

        history_parts = []

        for message in history:

            history_parts.append(
                f"{message['role'].upper()}: "
                f"{message['content']}"
            )

        history_text = "\n".join(
            history_parts
        )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are an AI assistant for Inquira.

Your job is to answer the user's question
using ONLY the provided document context.

Conversation history:
{history_text}

Document context:
{context_text}

Current question:
{question}

Rules:

1. Do not use outside knowledge.

2. Do not invent facts.

3. If the documents do not contain enough
   information, say:

   "I don't have enough information in the
   provided documents."

4. When you use information from a context
   chunk, cite it using [1], [2], [3], etc.

5. Only cite chunks that actually support
   your statement.

6. Use the conversation history only to
   understand what the user is referring to.

7. The document context is the source of
   factual information.

8. Give a clear and concise answer.

Answer:
"""

    # --------------------------------------------------------
    # Groq
    # --------------------------------------------------------

    response = client.chat.completions.create(

        model=settings.llm_model,

        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],

        temperature=0.2,
    )

    answer = response.choices[0].message.content

    # --------------------------------------------------------
    # Citations
    # --------------------------------------------------------

    citations = []

    for index, item in enumerate(
        contexts,
        start=1
    ):

        citations.append(
            {
                "id": index,
                "source": item.get("source"),
                "page": item.get("page"),
                "chunk_id": item.get("chunk_id"),
            }
        )

    return {
        "answer": answer,
        "citations": citations,
    }

def stream_answer(
    question: str,
    contexts: list[dict],
    history: list[dict] | None = None,
):
    context_parts = []

    for index, item in enumerate(contexts, start=1):
        context_parts.append(
            f"[{index}] {item['content']}"
        )

    context_text = "\n\n".join(context_parts)

    history_text = ""

    if history:
        history_parts = []

        for message in history:
            history_parts.append(
                f"{message['role'].upper()}: {message['content']}"
            )

        history_text = "\n".join(history_parts)

    prompt = f"""
You are an AI assistant for Inquira.

Answer the user's question using ONLY the provided
document context.

Conversation history:
{history_text}

Document context:
{context_text}

Current question:
{question}

Rules:
1. Do not use outside knowledge.
2. Do not invent facts.
3. If the documents do not contain enough information, say:
"I don't have enough information in the provided documents."
4. Cite information using [1], [2], [3], etc.
5. Only cite chunks that support the statement.
6. Use conversation history only to understand references.
7. The document context is the factual source.
8. Give a clear and concise answer.

Answer:
"""

    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.2,
        stream=True,
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content

        if content:
            yield content
# ============================================================
# VERIFY ANSWER
# ============================================================

def verify_answer(
    question: str,
    answer: str,
    contexts: list[dict],
) -> bool:

    context_text = "\n\n".join(
        item["content"]
        for item in contexts
    )

    prompt = f"""
You are a strict factual verifier.

Determine whether the answer is fully
supported by the provided context.

Question:
{question}

Context:
{context_text}

Answer:
{answer}

Return ONLY:

YES

if every factual claim in the answer
is supported by the context.

Return ONLY:

NO

if the answer contains information that
is not supported by the context.
"""

    response = client.chat.completions.create(

        model=settings.llm_model,

        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],

        temperature=0,
    )

    result = (
        response
        .choices[0]
        .message
        .content
        .strip()
        .upper()
    )

    return result == "YES"