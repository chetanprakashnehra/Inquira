from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.services.parser import ParsedPage
from app.config import settings


class ChunkItem:
    def __init__(self, chunk_index: int, page_number: int, content: str, token_count: int):
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.content = content
        self.token_count = token_count


class DocumentChunker:
    """Chunks structured parsed pages while retaining page boundaries and contiguous indexing."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator=True
        )

    def chunk_pages(self, pages: List[ParsedPage]) -> List[ChunkItem]:
        chunks: List[ChunkItem] = []
        global_chunk_idx = 0

        for page in pages:
            page_text = page.text
            if not page_text.strip():
                continue
            
            splits = self.splitter.split_text(page_text)
            for split in splits:
                if not split.strip():
                    continue
                # Rough token estimation (1 token ~ 4 chars)
                token_count = max(1, len(split) // 4)
                chunks.append(
                    ChunkItem(
                        chunk_index=global_chunk_idx,
                        page_number=page.page_number,
                        content=split.strip(),
                        token_count=token_count
                    )
                )
                global_chunk_idx += 1

        return chunks
