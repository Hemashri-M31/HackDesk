import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.schemas import ChatRequest, ChatResponse, TokenUsage, UsageEvent, UsageResponse, UsageSummary

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = 'Answer the user. Return only a JSON object with one string property named "answer".'
metadata = MetaData()
usage_events = Table(
    "usage_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("model", String(200), nullable=False),
    Column("prompt_tokens", Integer, nullable=False),
    Column("completion_tokens", Integer, nullable=False),
    Column("total_tokens", Integer, nullable=False),
    Column("estimated_cost_usd", Float, nullable=False),
)


def create_usage_engine(database_url: str) -> Engine:
    options: dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            options["poolclass"] = StaticPool
    return create_engine(database_url, **options)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings_provider = application.dependency_overrides.get(get_settings, get_settings)
    engine = create_usage_engine(settings_provider().database_url)
    metadata.create_all(engine)
    application.state.usage_engine = engine
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="HackDesk API", version="0.2.0", lifespan=lifespan)
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _cost_for_usage(settings: Settings, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if model == settings.llm_model:
        input_rate = settings.llm_input_cost_per_million
        output_rate = settings.llm_output_cost_per_million
    else:
        input_rate = settings.llm_fallback_input_cost_per_million
        output_rate = settings.llm_fallback_output_cost_per_million
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000


def _record_usage(
    engine: Engine,
    settings: Settings,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    total_tokens = prompt_tokens + completion_tokens
    cost = _cost_for_usage(settings, model, prompt_tokens, completion_tokens)
    with engine.begin() as connection:
        connection.execute(
            insert(usage_events).values(
                created_at=datetime.now(UTC),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost,
            )
        )
    return cost


async def _post_completion(
    settings: Settings,
    question: str,
    model: str,
    *,
    stream: bool = False,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    async with httpx.AsyncClient(
        base_url=settings.llm_base_url.rstrip("/") + "/",
        timeout=settings.llm_timeout_seconds,
    ) as client:
        response = await client.post("chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        return response


def _response_answer(response: httpx.Response) -> tuple[str, int, int]:
    try:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        structured = json.loads(content)
        answer = structured["answer"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer must be a non-empty string")
        usage = result.get("usage") or {}
        prompt_tokens = int(usage["prompt_tokens"])
        completion_tokens = int(usage["completion_tokens"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="LLM provider returned an invalid response") from error
    return answer, prompt_tokens, completion_tokens


async def _generate_answer(settings: Settings, question: str) -> tuple[str, str, int, int]:
    if not settings.llm_api_key:
        raise HTTPException(status_code=503, detail="LLM_API_KEY is not configured")
    models = [settings.llm_model]
    if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
        models.append(settings.llm_fallback_model)
    last_error: Exception | None = None
    for model in models:
        for attempt in range(settings.llm_retries + 1):
            try:
                response = await _post_completion(settings, question, model)
                answer, prompt_tokens, completion_tokens = _response_answer(response)
                return answer, model, prompt_tokens, completion_tokens
            except httpx.TimeoutException as error:
                last_error = error
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    last_error = error
                    break
                if error.response.status_code not in (408, 429) and error.response.status_code < 500:
                    raise HTTPException(
                        status_code=502,
                        detail="LLM provider rejected the request",
                    ) from error
                last_error = error
            except httpx.RequestError as error:
                last_error = error
            if attempt < settings.llm_retries:
                await asyncio.sleep(min(0.25 * (2**attempt), 2))
    logger.error("LLM request failed after retries and fallback: %s", type(last_error).__name__)
    raise HTTPException(status_code=502, detail="LLM provider is unavailable") from last_error


async def _stream_model(
    settings: Settings,
    question: str,
    model: str,
) -> AsyncIterator[tuple[str, dict[str, int] | None]]:
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    async with httpx.AsyncClient(
        base_url=settings.llm_base_url.rstrip("/") + "/",
        timeout=settings.llm_timeout_seconds,
    ) as client:
        async with client.stream(
            "POST",
            "chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as error:
                    raise HTTPException(
                        status_code=502,
                        detail="LLM provider returned invalid stream data",
                    ) from error
                usage = chunk.get("usage")
                if usage:
                    yield "", {
                        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                        "completion_tokens": int(usage.get("completion_tokens", 0)),
                    }
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {}).get("content")
                    if delta:
                        yield delta, None


async def _stream_response(
    settings: Settings,
    engine: Engine,
    question: str,
) -> AsyncIterator[str]:
    if not settings.llm_api_key:
        yield f"event: error\ndata: {json.dumps({'detail': 'LLM_API_KEY is not configured'})}\n\n"
        return
    models = [settings.llm_model]
    if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
        models.append(settings.llm_fallback_model)
    for model in models:
        for attempt in range(settings.llm_retries + 1):
            chunks: list[str] = []
            usage: dict[str, int] | None = None
            try:
                async for chunk, reported_usage in _stream_model(settings, question, model):
                    if reported_usage is not None:
                        usage = reported_usage
                    if chunk:
                        chunks.append(chunk)
                        yield f"data: {json.dumps({'delta': chunk})}\n\n"
                try:
                    answer = json.loads("".join(chunks))["answer"]
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError("answer must be a non-empty string")
                except (KeyError, TypeError, ValueError) as error:
                    raise HTTPException(
                        status_code=502,
                        detail="LLM provider returned an invalid response",
                    ) from error
                prompt_tokens = usage["prompt_tokens"] if usage else max(1, len(question) // 4)
                completion_tokens = usage["completion_tokens"] if usage else max(1, len(answer) // 4)
                _record_usage(engine, settings, model, prompt_tokens, completion_tokens)
                done_data = {
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
                yield f"event: done\ndata: {json.dumps(done_data)}\n\n"
                return
            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as error:
                status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                if status_code == 404 and not chunks:
                    break
                retryable = status_code is None or status_code in (408, 429) or status_code >= 500
                if not retryable or chunks:
                    detail = (
                        "LLM provider rejected the request"
                        if not retryable
                        else "LLM stream was interrupted"
                    )
                    yield f"event: error\ndata: {json.dumps({'detail': detail})}\n\n"
                    return
                if attempt < settings.llm_retries:
                    await asyncio.sleep(min(0.25 * (2**attempt), 2))
                    continue
            except HTTPException as error:
                yield f"event: error\ndata: {json.dumps({'detail': error.detail})}\n\n"
                return
        if model == models[-1]:
            break
    yield f"event: error\ndata: {json.dumps({'detail': 'LLM provider is unavailable'})}\n\n"


@app.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    """Liveness: the process is up. Must be fast and must not call the LLM or the DB."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, settings: SettingsDep):
    engine: Engine = request.app.state.usage_engine
    if payload.stream:
        return StreamingResponse(
            _stream_response(settings, engine, payload.question),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    answer, model, prompt_tokens, completion_tokens = await _generate_answer(settings, payload.question)
    _record_usage(engine, settings, model, prompt_tokens, completion_tokens)
    return ChatResponse(
        answer=answer,
        model=model,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@app.get("/usage", response_model=UsageResponse)
def usage(request: Request):
    engine: Engine = request.app.state.usage_engine
    with engine.connect() as connection:
        count, prompt_tokens, completion_tokens, total_tokens, cost = connection.execute(
            select(
                func.count(usage_events.c.id),
                func.coalesce(func.sum(usage_events.c.prompt_tokens), 0),
                func.coalesce(func.sum(usage_events.c.completion_tokens), 0),
                func.coalesce(func.sum(usage_events.c.total_tokens), 0),
                func.coalesce(func.sum(usage_events.c.estimated_cost_usd), 0.0),
            )
        ).one()
        rows = connection.execute(
            select(usage_events)
            .order_by(usage_events.c.created_at.desc(), usage_events.c.id.desc())
            .limit(100)
        ).mappings()
        recent = [
            UsageEvent(
                created_at=row["created_at"].isoformat(),
                model=row["model"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                total_tokens=row["total_tokens"],
                estimated_cost_usd=row["estimated_cost_usd"],
            )
            for row in rows
        ]
    return UsageResponse(
        summary=UsageSummary(
            requests=count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 8),
        ),
        recent=recent,
    )
