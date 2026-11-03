# HackDesk

An AI help desk for Next.js developers at large hackathons. HackDesk gives students fast, consistent answers to common questions about routing, caching, Server Components, and more, so mentors can spend less time repeating answers.

## Who it is for

Frontend trainers, hackathon organisers, and students building applications with Next.js.

## Signature feature

The planned Trending Questions Board will surface the ten most common questions and their answers. The current API foundation includes structured LLM answers, streaming, provider fallback, and usage-cost tracking.

## Hardest problem

Keeping answers responsive and affordable when many students ask similar questions. The planned solution is exact and semantic caching, followed by load testing at hackathon scale; neither caching nor the 10,000-user load test is implemented yet.

## Dataset

The dataset includes 60 App Router documentation pages from the [Next.js repository](https://github.com/vercel/next.js), with a pinned source revision, manifest, and three-page sample. See [DATASET.md](DATASET.md) for provenance and license details.

## Run locally

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Set LLM_API_KEY in .env to a key for your OpenAI-compatible provider.
uvicorn app.main:app --reload
```

The API starts without a key; `/health` and `/usage` work, while `/chat` returns `503` until `LLM_API_KEY` is configured. The default usage store is the local SQLite file `usage.db`.

## API

- `GET /health` — liveness check; does not call the provider or database.
- `POST /chat` — generate a JSON response with `answer`, `model`, and token usage.
- `POST /chat` with `"stream": true` — stream JSON deltas as Server-Sent Events; the final `done` event includes model and token counts.
- `GET /usage` — request/token totals, estimated cost, and the 100 latest requests.

Example request:

```json
{"question":"How do I create a dynamic route in the Next.js App Router?"}
```

Configure `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_FALLBACK_MODEL` for an OpenAI-compatible chat-completions provider. Retries and timeout are controlled with `LLM_RETRIES` and `LLM_TIMEOUT_SECONDS`. Cost estimates use the per-million-token rates in `.env`; keep them aligned with the provider's current pricing.

## Docker Compose

```powershell
Copy-Item .env.example .env
# Set LLM_API_KEY in .env if you want to call the model.
docker compose up --build
```

Compose starts the API and a persistent Postgres instance using the pgvector image. Usage events are stored in Postgres. The vector extension is not used until the retrieval work in Week 3. Open `http://localhost:8000/docs` for interactive API documentation.

## Deployment

No public deployment is configured yet.
