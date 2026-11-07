from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.parser import Chunk
from app.vector_store import (
    VectorStore,
    compute_deterministic_embedding,
    cosine_similarity,
)


def test_compute_deterministic_embedding_normalized():
    text1 = "How do I configure dynamic routes in Next.js?"
    text2 = "How to use dynamic routing in Next.js App Router?"
    text3 = "Unrelated cooking recipe about pasta and tomato sauce."

    emb1 = compute_deterministic_embedding(text1, dim=128)
    emb2 = compute_deterministic_embedding(text2, dim=128)
    emb3 = compute_deterministic_embedding(text3, dim=128)

    assert len(emb1) == 128
    sim_related = cosine_similarity(emb1, emb2)
    sim_unrelated = cosine_similarity(emb1, emb3)

    # Related questions should have higher similarity than completely unrelated topics
    assert sim_related > sim_unrelated


def test_vector_store_indexing_and_search():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    settings = Settings(embedding_dim=128)
    store = VectorStore(engine, settings)
    store.init_db()

    chunks = [
        Chunk(
            document="01-installation.mdx",
            page=1,
            heading="Installation > Quick Start",
            content="Run npx create-next-app to initialize a new project.",
            chunk_index=0,
            metadata={"title": "Installation"},
        ),
        Chunk(
            document="05-server-and-client-components.mdx",
            page=2,
            heading="Client Components > Use Client",
            content="Use the 'use client' directive at the top of a file to declare a Client Component.",
            chunk_index=1,
            metadata={"title": "Server and Client Components"},
        ),
    ]

    embs = [compute_deterministic_embedding(c.content, dim=128) for c in chunks]
    count = store.add_chunks(chunks, embs)
    assert count == 2

    # Query search
    query = "How do I declare a client component with use client directive?"
    q_vec = compute_deterministic_embedding(query, dim=128)
    results = store.search(q_vec, top_k=2, query_text=query)

    assert len(results) == 2
    assert results[0].document == "05-server-and-client-components.mdx"
    assert results[0].page == 2
    assert "use client" in results[0].content

