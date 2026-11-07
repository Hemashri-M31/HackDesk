from app.parser import MarkdownDocumentParser, ParsedPage


SAMPLE_MDX = """---
title: Server and Client Components
description: Understanding React Server Components in Next.js
---

<AppOnly>
Next.js App Router uses React Server Components by default.
</AppOnly>

# Server Components

Server Components allow developers to build applications that span the server and client.
By rendering on the server, you can reduce the amount of JavaScript sent to the client.

## Benefits of Server Components

- Data fetching closer to the data source
- Security: keep sensitive tokens on the server
- Caching: results can be cached across requests

# Client Components

Client Components allow you to add client-side interactivity to your application.
In Next.js, they are pre-rendered on the server and hydrated in the browser.

## The use client directive

To declare a Client Component, add the React "use client" directive at the top of your file.
This creates a boundary between Server and Client component modules.
"""


def test_parser_extracts_frontmatter_and_headings():
    parser = MarkdownDocumentParser(chars_per_page=400, chunk_size=300)
    pages = parser.parse_to_pages(SAMPLE_MDX, "05-server-and-client-components.mdx")

    assert len(pages) >= 2
    assert pages[0].document == "05-server-and-client-components.mdx"
    assert pages[0].page == 1
    assert "Server Components" in pages[0].headings
    assert pages[0].metadata.get("title") == "Server and Client Components"

    # Verify later page maintains page numbering and updated headings
    assert pages[1].page == 2
    assert any("Client Components" in h or "Benefits" in h for h in pages[1].headings)


def test_chunking_preserves_page_numbers_and_citations():
    parser = MarkdownDocumentParser(chars_per_page=500, chunk_size=250, chunk_overlap=50)
    page = ParsedPage(
        document="08-caching.mdx",
        page=3,
        headings=["Caching", "Data Cache"],
        content="Next.js provides built-in data caching using fetch extensions.\n\nRevalidation can be time-based or on-demand using revalidateTag.",
        metadata={"title": "Caching in Next.js"},
    )
    chunks = parser.chunk_page(page, start_index=0)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.document == "08-caching.mdx"
        assert chunk.page == 3
        assert chunk.citation == "[08-caching.mdx, page 3]"
        assert "Caching" in chunk.heading


def test_parser_strips_mdx_tags():
    parser = MarkdownDocumentParser()
    raw = "<AppOnly>\nHello App Router\n</AppOnly>\n{/* comment */}\nNormal text"
    cleaned = parser.strip_mdx_tags(raw)
    assert "<AppOnly>" not in cleaned
    assert "</AppOnly>" not in cleaned
    assert "{/* comment */}" not in cleaned
    assert "Hello App Router" in cleaned
    assert "Normal text" in cleaned
