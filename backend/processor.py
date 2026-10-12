from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chunker import TextChunker
from document_loader import DocumentLoader
from embeddings import embed_text
from models import Document, DocumentChunk
from qdrant import insert_embedding


loader = DocumentLoader()

chunker = TextChunker(
    chunk_size=800,
    chunk_overlap=150,
)


async def process_document(
    document: Document,
    db: AsyncSession,
):

    result = loader.load(document.file_path)

    total_chunks = 0

    for loaded_document in result["documents"]:

        text = loaded_document["text"]

        metadata = loaded_document["metadata"]

        chunks = chunker.chunk(
            text,
            metadata,
        )

        for chunk_data in chunks:

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=total_chunks,
                content=chunk_data["text"],
                page_number=chunk_data["metadata"].get("page"),
            )

            db.add(chunk)

            await db.flush()

            vector = embed_text(
                chunk.content
            )

            insert_embedding(
                point_id=str(chunk.id),
                vector=vector,
                payload={
                    "document_id": str(document.id),
                    "chunk_id": str(chunk.id),
                    "source": document.filename,
                    "page": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                },
            )

            chunk.qdrant_point_id = str(chunk.id)

            total_chunks += 1

    document.chunk_count = total_chunks
    document.status = "processed"

    await db.commit()

    return total_chunks