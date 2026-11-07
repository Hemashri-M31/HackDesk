# HackDesk

An AI help desk for Next.js developers at large hackathons. HackDesk gives students fast, consistent answers to common questions about routing, caching, Server Components, and more, so mentors can spend less time repeating answers.

## Who it is for

Frontend trainers, hackathon organisers, and students building applications with Next.js.

## Signature feature

The planned Trending Questions Board will surface the ten most common questions and their answers. The API includes:
- Grounded retrieval with `[document, page]` citations via `POST /ask`
- Structured LLM answers and streaming deltas via `POST /chat`
- Multi-tier provider fallback, automated retries, and usage/cost logging via `GET /usage`
- Vector storage with pgvector and SQLite fallback support

## Hardest problem

Keeping answers responsive and affordable when 2,000 students ask similar questions concurrently. Planned for Week 4 is exact and semantic Redis caching and load testing at 10,000 simulated users targeting a p95 latency under 1 second and 60%+ cache hit rate.

## Dataset

The dataset includes **520 Next.js documentation and guide pages** from the [Next.js repository](https://github.com/vercel/next.js) (App Router, Pages Router, Architecture, and Examples), yielding **3,365 logical pages** and **6,781 indexed chunks**. See [DATASET.md](DATASET.md) for provenance, manifest, and MIT license details.

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

The API starts without a key; `/health` and `/usage` work, while `/chat` and `/ask` return `503` until `LLM_API_KEY` is configured. The default usage and vector store is the local SQLite file `usage.db`.

To index documents into the database:

```powershell
python -m app.indexer
```

## API Endpoints

- `GET /health` — liveness check; does not call the provider or database.
- `POST /ask` — answers student questions using RAG with inline citations in the format `[document, page]` and a structured list of citations and retrieved chunks.
- `POST /chat` — generate a JSON response with `answer`, `model`, and token usage.
- `POST /chat` with `"stream": true` — stream JSON deltas as Server-Sent Events; the final `done` event includes model and token counts.
- `GET /usage` — request/token totals, estimated cost, and the 100 latest requests.

Example `POST /ask` request:

```json
{
  "question": "What is the difference between a server component and a client component in the code?",
  "top_k": 4
}
```

Example `POST /ask` response:

```json
{
  "question": "What is the difference between a server component and a client component in the code?",
  "answer": "In Next.js App Router, components are Server Components by default [05-server-and-client-components.mdx, page 1]. Server Components execute on the server and add zero bytes to the client JavaScript bundle. Client Components require the 'use client' directive at the top of the file to use browser APIs and React state hooks [05-server-and-client-components.mdx, page 2].",
  "citations": [
    {
      "document": "sample/05-server-and-client-components.mdx",
      "page": 1,
      "heading": "Server Components"
    },
    {
      "document": "sample/05-server-and-client-components.mdx",
      "page": 2,
      "heading": "Client Components"
    }
  ],
  "model": "gpt-4o-mini",
  "usage": {
    "prompt_tokens": 340,
    "completion_tokens": 82,
    "total_tokens": 422
  }
}
```

## Docker Compose

```powershell
Copy-Item .env.example .env
# Set LLM_API_KEY in .env if you want to call the model.
docker compose up --build
```

Compose starts the API and a persistent Postgres instance using the `pgvector/pgvector:pg16` image.

## Baseline Evaluation

See [docs/EVAL_v0.md](docs/EVAL_v0.md) for the baseline evaluation of all 10 benchmark questions, rubric scores, and error analysis.
