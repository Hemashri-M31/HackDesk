import hashlib
import json
import logging
import math
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Engine

from app.config import Settings
from app.parser import Chunk
from app.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

PGVECTOR_AVAILABLE = False
try:
    import pgvector  # noqa: F401

    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False

metadata = MetaData()

documents_table = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("doc_path", String(500), unique=True, nullable=False),
    Column("title", String(500), nullable=True),
    Column("total_pages", Integer, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

chunks_table = Table(
    "document_chunks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id"), nullable=True),
    Column("doc_path", String(500), nullable=False),
    Column("page", Integer, nullable=False, default=1),
    Column("heading", String(500), nullable=True),
    Column("content", Text, nullable=False),
    Column("chunk_index", Integer, nullable=False, default=0),
    Column("metadata_json", Text, nullable=True),
    Column("embedding_json", Text, nullable=True),
)


def compute_deterministic_embedding(text_value: str, dim: int = 1536) -> list[float]:
    """Pure-Python deterministic dense embedding for offline use, fallback, and reproducible testing.

    Generates a normalized dense vector using character n-grams and token hashes.
    """
    cleaned = text_value.lower()
    tokens = re.findall(r"\b[a-z0-9_]{2,}\b", cleaned)
    features: dict[int, float] = {}

    for token in tokens:
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        features[idx] = features.get(idx, 0.0) + 2.0

    for i in range(len(cleaned) - 2):
        trigram = cleaned[i : i + 3]
        idx = int(hashlib.sha256(trigram.encode("utf-8")).hexdigest(), 16) % dim
        features[idx] = features.get(idx, 0.0) + 1.0

    vec = [0.0] * dim
    for idx, val in features.items():
        vec[idx] = val

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(v1) != len(v2) or not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def generate_embedding(
    text_content: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> list[float]:
    """Generate an embedding using configured provider or deterministic fallback."""
    dim = settings.embedding_dim

    if settings.llm_api_key:
        base_url = settings.llm_base_url.rstrip("/") + "/"
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        payload = {
            "model": settings.embedding_model,
            "input": text_content,
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(base_url=base_url, timeout=settings.llm_timeout_seconds)
            should_close = True

        try:
            resp = await client.post("embeddings", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["data"][0]["embedding"]
            logger.warning(
                "Embedding API returned status %s; falling back to deterministic embedding.",
                resp.status_code,
            )
        except Exception as exc:
            logger.warning("Embedding API call failed (%s); using deterministic embedding.", exc)
        finally:
            if should_close:
                await client.aclose()

    return compute_deterministic_embedding(text_content, dim=dim)


class VectorStore:
    """Handles document indexing and semantic retrieval across SQLite and Postgres/pgvector."""

    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.is_postgres = not str(engine.url).startswith("sqlite")
        self.chunks_table = chunks_table

    def init_db(self) -> None:
        """Create extension and tables if they do not exist."""
        with self.engine.begin() as conn:
            if self.is_postgres:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            metadata.create_all(conn)
            if self.is_postgres:
                # Add native pgvector vector column if not already present
                conn.execute(
                    text(
                        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS "
                        f"embedding vector({self.settings.embedding_dim});"
                    )
                )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """Index chunks and their embeddings into the store."""
        if not chunks:
            return 0

        with self.engine.begin() as conn:
            docs_map: dict[str, int] = {}
            for chunk in chunks:
                if chunk.document not in docs_map:
                    existing = conn.execute(
                        select(documents_table.c.id).where(documents_table.c.doc_path == chunk.document)
                    ).scalar_one_or_none()
                    if existing is not None:
                        docs_map[chunk.document] = existing
                    else:
                        title = chunk.metadata.get("title") or chunk.heading
                        res = conn.execute(
                            insert(documents_table).values(
                                doc_path=chunk.document,
                                title=title,
                                total_pages=chunk.page,
                                created_at=datetime.now(UTC),
                            )
                        )
                        docs_map[chunk.document] = res.inserted_primary_key[0]

            rows_to_insert = []
            for chunk, emb in zip(chunks, embeddings, strict=True):
                doc_id = docs_map.get(chunk.document)
                row_data: dict[str, Any] = {
                    "document_id": doc_id,
                    "doc_path": chunk.document,
                    "page": chunk.page,
                    "heading": chunk.heading,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "metadata_json": json.dumps(chunk.metadata),
                    "embedding_json": json.dumps(emb),
                }
                rows_to_insert.append(row_data)

            if rows_to_insert:
                conn.execute(insert(self.chunks_table), rows_to_insert)
                if self.is_postgres:
                    # Update vector embeddings for pgvector column
                    for r, emb in zip(rows_to_insert, embeddings, strict=True):
                        conn.execute(
                            text(
                                "UPDATE document_chunks SET embedding = :emb "
                                "WHERE doc_path = :doc AND chunk_index = :idx"
                            ),
                            {
                                "emb": str(emb),
                                "doc": r["doc_path"],
                                "idx": r["chunk_index"],
                            },
                        )

        return len(rows_to_insert)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 4,
        query_text: str = "",
    ) -> list[RetrievedChunk]:
        """Search top-k most similar chunks using cosine similarity or pgvector distance."""
        if self.is_postgres:
            sql = f"""
                SELECT doc_path, page, heading, content,
                       1 - (embedding <=> :vec) AS score
                FROM {self.chunks_table.name}
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :vec
                LIMIT :limit
            """
            with self.engine.connect() as conn:
                results = conn.execute(
                    text(sql),
                    {"vec": str(query_vector), "limit": top_k},
                ).mappings()
                return [
                    RetrievedChunk(
                        document=row["doc_path"],
                        page=row["page"],
                        heading=row["heading"],
                        content=row["content"],
                        score=float(row["score"]),
                    )
                    for row in results
                ]

        with self.engine.connect() as conn:
            rows = conn.execute(
                select(
                    self.chunks_table.c.doc_path,
                    self.chunks_table.c.page,
                    self.chunks_table.c.heading,
                    self.chunks_table.c.content,
                    self.chunks_table.c.embedding_json,
                )
            ).mappings()

            scored: list[RetrievedChunk] = []
            q_lower = query_text.lower()
            q_keywords = set(re.findall(r"\b\w{3,}\b", q_lower))

            for row in rows:
                emb_raw = row["embedding_json"]
                if not emb_raw:
                    continue
                emb = json.loads(emb_raw)
                score = cosine_similarity(query_vector, emb)

                if q_keywords:
                    c_lower = row["content"].lower()
                    h_lower = (row["heading"] or "").lower()
                    match_count = sum(1 for kw in q_keywords if kw in c_lower or kw in h_lower)
                    if match_count:
                        score += 0.05 * min(match_count, 3)

                scored.append(
                    RetrievedChunk(
                        document=row["doc_path"],
                        page=row["page"],
                        heading=row["heading"],
                        content=row["content"],
                        score=round(float(score), 4),
                    )
                )

            scored.sort(key=lambda x: x.score, reverse=True)
            return scored[:top_k]
