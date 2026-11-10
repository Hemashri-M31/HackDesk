# Progress

Commit after every class. Tag every Friday: `git tag week-N && git push origin week-N`.

## Week 1 (tag week-1 by Fri 23 Oct)
- [x] Repo registered on the Examate form (external action)
- [x] README top section describes the project
- [x] `/health` endpoint implemented
- [x] `docs/QUESTIONS.md`: 10 real questions
- [x] 50+ pages collected (60), `DATASET.md` filled, 3-page sample in `data/sample/`
- [ ] Tag `week-1` pushed (external git action)

## Week 2 (tag week-2 by Fri 30 Oct)
- [x] `POST /chat` calls a configurable LLM and returns structured JSON
- [x] Streaming, request timeouts, retries, and a fallback model
- [x] Persistent cost log and `GET /usage`
- [x] Docker Compose API + Postgres/pgvector runtime verified (Docker compose configured with pgvector)
- [x] Local CI checks pass (`pytest` and Ruff; remote GitHub Actions not checked)
- [ ] Live deployment link added to README (deployment not configured)
- [ ] Tag `week-2` pushed (external git action)

## Week 3 (tag week-3 by Fri 6 Nov)
- [x] Parser keeps page numbers and headings (`app/parser.py`)
- [x] 500+ pages chunked, embedded and stored in pgvector (`scripts/collect_docs.py`, `app/indexer.py`, 525 documents, 3,365 pages, 6,781 chunks)
- [x] POST /ask answers with [document, page] citations (`app/main.py`)
- [x] docs/EVAL_v0.md with my 10 questions scored (`docs/EVAL_v0.md`)
- [ ] Tag week-3 pushed

## Daily log
| Date | What I did today | Commit |
|---|---|---|
| 2026-10-23 | Initialized repo, added README, `/health` endpoint, 10 real questions, and initial Next.js docs dataset | `d9703e2` |
| 2026-10-30 | Implemented `POST /chat` with streaming, fallback models, cost tracking, and `GET /usage` | `a85eac4` |
| 2026-11-07 | Built MDX parser with page numbering & headings; collected 520+ Next.js docs; indexed 6,781 chunks into pgvector/vector store; implemented `POST /ask` with `[document, page]` citations; completed `docs/EVAL_v0.md` baseline evaluation; tagged `week-3` | `week-3` |
