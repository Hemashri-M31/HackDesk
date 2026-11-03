import json

import httpx

from app import main
from app.config import Settings, get_settings


def test_chat_returns_structured_answer_and_tracks_cost(client, monkeypatch):
    async def fake_post_completion(settings, question, model, *, stream=False):
        assert question == "How do I route?"
        assert model == settings.llm_model
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"answer": "Use a dynamic segment."})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6},
            },
            request=httpx.Request("POST", "https://provider.test/chat/completions"),
        )

    monkeypatch.setattr(main, "_post_completion", fake_post_completion)
    response = client.post("/chat", json={"question": "How do I route?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Use a dynamic segment.",
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
    }
    usage = client.get("/usage").json()
    assert usage["summary"]["requests"] == 1
    assert usage["summary"]["total_tokens"] == 16
    assert usage["summary"]["estimated_cost_usd"] == 0.0000051
    assert usage["recent"][0]["model"] == "gpt-4o-mini"


def test_chat_retries_then_uses_fallback_model(client, monkeypatch):
    called_models = []

    async def fake_post_completion(settings, question, model, *, stream=False):
        called_models.append(model)
        if model == settings.llm_model:
            raise httpx.TimeoutException("provider timed out")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"answer": "Fallback answer."})}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            },
            request=httpx.Request("POST", "https://provider.test/chat/completions"),
        )

    monkeypatch.setattr(main, "_post_completion", fake_post_completion)
    response = client.post("/chat", json={"question": "Question"})

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4.1-mini"
    assert called_models == ["gpt-4o-mini"] * 3 + ["gpt-4.1-mini"]


def test_chat_requires_provider_key(client):
    main.app.dependency_overrides[get_settings] = lambda: Settings(
        llm_api_key="",
        database_url="sqlite:///:memory:",
    )

    response = client.post("/chat", json={"question": "Question"})

    assert response.status_code == 503
    assert response.json()["detail"] == "LLM_API_KEY is not configured"


def test_streaming_chat_emits_answer_and_tracks_usage(client, monkeypatch):
    async def fake_stream_model(settings, question, model):
        yield '{"answer":', None
        yield '"Streamed answer."}', None
        yield "", {"prompt_tokens": 12, "completion_tokens": 5}

    monkeypatch.setattr(main, "_stream_model", fake_stream_model)
    response = client.post("/chat", json={"question": "Question", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"delta": "{\\"answer\\":"' in response.text
    assert "event: done" in response.text
    assert '"model": "gpt-4o-mini"' in response.text
    usage = client.get("/usage").json()
    assert usage["summary"]["requests"] == 1
    assert usage["summary"]["total_tokens"] == 17
