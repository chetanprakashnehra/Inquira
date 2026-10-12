from google import genai
from google.genai import types

from config import settings


client = genai.Client(
    api_key=settings.gemini_api_key
)


def embed_text(text: str) -> list[float]:

    response = client.models.embed_content(
        model=settings.dense_embedding_model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=settings.dense_embedding_dim
        ),
    )

    return response.embeddings[0].values