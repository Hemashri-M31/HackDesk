import json

import httpx

from app import main
from app.config import Settings, get_settings
from app.parser import Chunk
from app.vector_store import compute_deterministic_embedding


def test_ask_returns_answer_with_citations_and_tracks_cost(client, monkeypatch):
    # Seed vector store with sample chunks
    vector_store = main.app.state.vector_store
    chunk = Chunk(
        document="05-server-and-client-components.mdx",
        page=1,
        heading="Server Components",
        content="Server Components run entirely on the server and send no JavaScript bundle to the browser.",
        chunk_index=0,
        metadata={"title": "Server Components"},
    )
    emb = compute_deterministic_embedding(chunk.content, dim=1536)
    vector_store.add_chunks([chunk], [emb])

    fake_rag_response = {
        "answer": (
            "Server Components execute on the server and do not add JavaScript to the client bundle "
            "[05-server-and-client-components.mdx, page 1]."
        ),
        "citations": [
            {
                "document": "05-server-and-client-components.mdx",
                "page": 1,
                "heading": "Server Components",
            }
        ],
    }

    async def fake_post_completion(settings, question, model, *, system_prompt="", stream=False):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(fake_rag_response)}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30},
            },
            request=httpx.Request("POST", "https://provider.test/chat/completions"),
        )

    monkeypatch.setattr(main, "_post_completion", fake_post_completion)

    response = client.post(
        "/ask",
        json={"question": "What is the difference between server and client components?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "[05-server-and-client-components.mdx, page 1]" in data["answer"]
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["document"] == "05-server-and-client-components.mdx"
    assert data["citations"][0]["page"] == 1
    assert data["model"] == "gpt-4o-mini"
    assert data["usage"]["total_tokens"] == 150

    # Verify usage was tracked
    usage = client.get("/usage").json()
    assert usage["summary"]["requests"] >= 1
    assert usage["summary"]["total_tokens"] >= 150


def test_ask_requires_provider_key(client):
    main.app.dependency_overrides[get_settings] = lambda: Settings(
        llm_api_key="",
        database_url="sqlite:///:memory:",
    )

    response = client.post("/ask", json={"question": "How do I cache responses?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "LLM_API_KEY is not configured"


def test_ask_handles_unanswerable_question(client, monkeypatch):
    fake_refusal_response = {
        "answer": (
            "Based on the provided Next.js documentation, this information is not available. "
            "Server capacity and crash diagnostics under 2,000 users require deployment infrastructure logs."
        ),
        "citations": [],
    }

    async def fake_post_completion(settings, question, model, *, system_prompt="", stream=False):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(fake_refusal_response)}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 25},
            },
            request=httpx.Request("POST", "https://provider.test/chat/completions"),
        )

    monkeypatch.setattr(main, "_post_completion", fake_post_completion)

    response = client.post(
        "/ask",
        json={"question": "Why is my server crashing with 2,000 students?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "not available" in data["answer"].lower()
