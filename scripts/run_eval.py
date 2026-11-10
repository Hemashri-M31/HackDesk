import json

from sqlalchemy import create_engine

from app.config import Settings
from app.vector_store import VectorStore, compute_deterministic_embedding

engine = create_engine("sqlite:///./usage.db")
settings = Settings()
store = VectorStore(engine, settings)

QUESTIONS = [
    {
        "id": 1,
        "question": (
            "How do I create a dynamic route in Next.js App Router to display details "
            "for each product using its ID?"
        ),
        "intended_source": "Dynamic Routes",
        "expected": (
            "Wrap folder name in square brackets: app/products/[id]/page.tsx. Access "
            "params in page component props: ({ params }: { params: { id: string } })."
        ),
    },
    {
        "id": 2,
        "question": (
            "What is the difference between page.tsx, layout.tsx, and template.tsx in "
            "Next.js?"
        ),
        "intended_source": "Pages, Layouts, Templates",
        "expected": (
            "page.tsx defines UI unique to a route; layout.tsx defines shared UI that "
            "preserves state across navigation; template.tsx creates a new instance on "
            "navigation without preserving state."
        ),
    },
    {
        "id": 3,
        "question": (
            "How does caching work in Next.js, and how can I revalidate cached data "
            "when it changes?"
        ),
        "intended_source": "Caching, revalidatePath, revalidateTag",
        "expected": (
            "Next.js uses multi-tier caching (Request Memoization, Data Cache, Full Route "
            "Cache, Router Cache). Revalidation can be time-based (next: { revalidate: "
            "60 }) or on-demand via revalidateTag() or revalidatePath()."
        ),
    },
    {
        "id": 4,
        "question": (
            "Why is my API request returning stale data in Next.js, and how can I refresh "
            "it without rebuilding the entire application?"
        ),
        "intended_source": "Data Fetching, Caching, Revalidating",
        "expected": (
            "fetch requests in Next.js are cached by default in the Data Cache. Use "
            "cache: 'no-store' or next: { revalidate: 0 } or trigger on-demand "
            "revalidation using revalidateTag / revalidatePath."
        ),
    },
    {
        "id": 5,
        "question": (
            "What is the difference between Server Components and Client Components, and "
            "when should I use the 'use client' directive?"
        ),
        "intended_source": "Server and Client Components",
        "expected": (
            "Server Components run exclusively on the server, saving bundle size. Client "
            "Components allow interactive React hooks (useState, useEffect, event "
            "listeners). Add 'use client' at the top of file to mark as client."
        ),
    },
    {
        "id": 6,
        "question": (
            'Why am I getting the error "You\'re importing a component that needs '
            'useState. It only works in a Client Component"?'
        ),
        "intended_source": "Server and Client Components",
        "expected": (
            "useState is a React hook available only in Client Components. Because App "
            "Router components are Server Components by default, you must add 'use "
            "client' at the very top of the file."
        ),
    },
    {
        "id": 7,
        "question": "How can I optimize images in Next.js to improve page loading speed?",
        "intended_source": "next/image Component",
        "expected": (
            "Use the next/image component (`import Image from 'next/image'`). It provides "
            "automatic sizing, WebP/AVIF format serving, lazy loading, and prevents "
            "Cumulative Layout Shift (CLS)."
        ),
    },
    {
        "id": 8,
        "question": (
            "My Next.js application becomes slow when many users access it "
            "simultaneously. How can I identify and fix the performance bottleneck?"
        ),
        "intended_source": "Production Performance, Caching, Deployment",
        "expected": (
            "Identify bottleneck via server logs/instrumentation. Fixes include caching "
            "dynamic fetches, using ISR, offloading static assets to CDN, optimizing "
            "database queries, and utilizing server component streaming."
        ),
    },
    {
        "id": 9,
        "question": (
            "How do I create an API endpoint using Route Handlers in Next.js App Router, "
            "and how do I handle errors properly?"
        ),
        "intended_source": "Route Handlers, route.ts",
        "expected": (
            "Create a route.ts inside the app folder (e.g., app/api/items/route.ts). "
            "Export HTTP methods (GET, POST). Use NextResponse.json() and try/catch "
            "blocks returning appropriate status codes like 400 or 500."
        ),
    },
    {
        "id": 10,
        "question": (
            "Why is my deployed Hack Desk server crashing when 2,000 students access it "
            "simultaneously, and what is the exact maximum number of users my server "
            "can handle?"
        ),
        "intended_source": "None (Unanswerable from Next.js docs)",
        "expected": (
            "Refusal / Abstention: The Next.js framework documentation does not contain "
            "user deployment server hardware specifications, concurrency limits, or "
            "specific crash diagnostics for HackDesk. Requires server logs and load "
            "testing."
        ),
    },
]


def run_eval():
    eval_results = []
    for item in QUESTIONS:
        qid = item["id"]
        q = item["question"]
        q_vec = compute_deterministic_embedding(q, dim=1536)
        retrieved = store.search(q_vec, top_k=3, query_text=q)

        top_chunk = retrieved[0] if retrieved else None
        top_doc = top_chunk.document if top_chunk else "none"
        top_page = top_chunk.page if top_chunk else 0
        top_heading = top_chunk.heading if top_chunk else "none"
        score = top_chunk.score if top_chunk else 0.0

        eval_results.append(
            {
                "id": qid,
                "question": q,
                "top_doc": top_doc,
                "top_page": top_page,
                "top_heading": top_heading,
                "score": score,
                "all_matches": [f"[{r.document}, p.{r.page}] (score: {r.score:.3f})" for r in retrieved],
            }
        )

    print(json.dumps(eval_results, indent=2))


if __name__ == "__main__":
    run_eval()
