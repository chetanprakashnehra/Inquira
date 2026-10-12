class TextChunker:

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        text: str,
        metadata: dict | None = None,
    ) -> list[dict]:

        if not text.strip():
            return []

        metadata = metadata or {}

        pieces = self._split_text(text)

        chunks = []
        current = ""

        for piece in pieces:

            piece = piece.strip()

            if not piece:
                continue

            if len(current) + len(piece) + 1 <= self.chunk_size:
                current = (
                    f"{current} {piece}"
                    if current
                    else piece
                )

            else:
                if current:
                    chunks.append(current)

                current = piece

        if current:
            chunks.append(current)

        return self._add_metadata(
            chunks,
            metadata,
        )

    def _split_text(self, text: str) -> list[str]:

        separators = [
            "\n\n",
            "\n",
            ". ",
            " ",
        ]

        pieces = [text]

        for separator in separators:

            new_pieces = []

            for piece in pieces:

                if len(piece) <= self.chunk_size:
                    new_pieces.append(piece)
                    continue

                split_parts = piece.split(separator)

                for part in split_parts:
                    if part.strip():
                        new_pieces.append(part)

            pieces = new_pieces

        return pieces

    def _add_metadata(
        self,
        chunks: list[str],
        metadata: dict,
    ) -> list[dict]:

        result = []

        for index, chunk in enumerate(chunks):

            result.append(
                {
                    "text": chunk,
                    "metadata": {
                        **metadata,
                        "chunk_index": index,
                    },
                }
            )

        return result