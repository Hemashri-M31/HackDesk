import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedPage:
    document: str
    page: int
    headings: list[str]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    document: str
    page: int
    heading: str
    content: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        """Returns citation tag in the format: [document, page]"""
        return f"[{self.document}, page {self.page}]"


class MarkdownDocumentParser:
    """Parser for Markdown and MDX documents that preserves headings and page numbers."""

    def __init__(
        self,
        chars_per_page: int = 1200,
        chunk_size: int = 750,
        chunk_overlap: int = 120,
    ) -> None:
        self.chars_per_page = chars_per_page
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def strip_mdx_tags(self, text: str) -> str:
        """Strip MDX components like <AppOnly>, <PagesOnly>, or HTML tags while retaining text."""
        # Remove JSX self-closing comments and tags like {/* ... */}
        text = re.sub(r"\{\/\*[\s\S]*?\*\/\}/?", "", text)
        # Remove JSX container tags like <AppOnly>, </AppOnly>, <PagesOnly>, etc.
        text = re.sub(r"<\/?(AppOnly|PagesOnly|Tabs|Tab|Callout|Note|Info|Check)[^>]*>", "", text)
        return text

    def extract_frontmatter(self, text: str) -> tuple[dict[str, str], str]:
        """Extract YAML-style frontmatter between --- fences."""
        metadata: dict[str, str] = {}
        cleaned_text = text
        if text.startswith("---"):
            match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n", text)
            if match:
                raw_fm = match.group(1)
                cleaned_text = text[match.end() :]
                for line in raw_fm.splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip().strip("\"'")
        return metadata, cleaned_text

    def parse_to_pages(self, content: str, document_name: str) -> list[ParsedPage]:
        """Parse raw markdown/MDX content into logical pages while tracking headings."""
        frontmatter, body = self.extract_frontmatter(content)
        cleaned = self.strip_mdx_tags(body)

        title = frontmatter.get("title", "")
        current_headings: list[str] = [title] if title else []

        # Split into paragraphs/blocks
        blocks = re.split(r"(\r?\n){2,}", cleaned)
        blocks = [b.strip() for b in blocks if b and b.strip()]

        pages: list[ParsedPage] = []
        current_page_num = 1
        current_page_blocks: list[str] = []
        current_page_headings: set[str] = set(current_headings)
        current_char_count = 0

        heading_regex = re.compile(r"^(#{1,6})\s+(.+)$")

        for block in blocks:
            # Check if block contains headings
            lines = block.splitlines()
            for line in lines:
                h_match = heading_regex.match(line.strip())
                if h_match:
                    level = len(h_match.group(1))
                    h_text = h_match.group(2).strip()
                    # Adjust heading stack to match depth
                    if level <= len(current_headings):
                        current_headings = current_headings[: level - 1]
                    current_headings.append(h_text)
                    current_page_headings.add(h_text)

            block_len = len(block)
            # If current page exceeds target chars_per_page and has content, flush page
            if current_char_count + block_len > self.chars_per_page and current_page_blocks:
                page_text = "\n\n".join(current_page_blocks).strip()
                headings_list = sorted(list(current_page_headings))
                pages.append(
                    ParsedPage(
                        document=document_name,
                        page=current_page_num,
                        headings=headings_list,
                        content=page_text,
                        metadata=dict(frontmatter),
                    )
                )
                current_page_num += 1
                current_page_blocks = [block]
                current_char_count = block_len
                current_page_headings = set(current_headings)
            else:
                current_page_blocks.append(block)
                current_char_count += block_len

        # Flush final page
        if current_page_blocks:
            page_text = "\n\n".join(current_page_blocks).strip()
            headings_list = sorted(list(current_page_headings))
            pages.append(
                ParsedPage(
                    document=document_name,
                    page=current_page_num,
                    headings=headings_list,
                    content=page_text,
                    metadata=dict(frontmatter),
                )
            )

        if not pages:
            # Empty document fallback
            pages.append(
                ParsedPage(
                    document=document_name,
                    page=1,
                    headings=[title] if title else [],
                    content="",
                    metadata=dict(frontmatter),
                )
            )

        return pages

    def chunk_page(self, page: ParsedPage, start_index: int = 0) -> list[Chunk]:
        """Split a ParsedPage into overlapping chunks while preserving page number and headings."""
        heading_title = " > ".join(page.headings) if page.headings else page.document
        text = page.content.strip()
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [
                Chunk(
                    document=page.document,
                    page=page.page,
                    heading=heading_title,
                    content=text,
                    chunk_index=start_index,
                    metadata=dict(page.metadata),
                )
            ]

        chunks: list[Chunk] = []
        pos = 0
        idx = start_index

        while pos < len(text):
            end = min(pos + self.chunk_size, len(text))
            # Try to break at paragraph or newline or sentence
            if end < len(text):
                split_pos = text.rfind("\n\n", pos + self.chunk_size // 2, end)
                if split_pos == -1:
                    split_pos = text.rfind("\n", pos + self.chunk_size // 2, end)
                if split_pos == -1:
                    split_pos = text.rfind(". ", pos + self.chunk_size // 2, end)
                    if split_pos != -1:
                        split_pos += 1  # include period
                if split_pos != -1:
                    end = split_pos

            chunk_text = text[pos:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        document=page.document,
                        page=page.page,
                        heading=heading_title,
                        content=chunk_text,
                        chunk_index=idx,
                        metadata=dict(page.metadata),
                    )
                )
                idx += 1

            if end >= len(text):
                break
            pos = max(pos + 1, end - self.chunk_overlap)

        return chunks

    def parse_file(self, file_path: Path | str, base_dir: Path | str | None = None) -> list[Chunk]:
        """Parse a single file from disk and return its chunks with page numbers and headings."""
        path = Path(file_path)
        if base_dir:
            try:
                doc_name = str(path.relative_to(Path(base_dir))).replace("\\", "/")
            except ValueError:
                doc_name = path.name
        else:
            doc_name = path.name

        content = path.read_text(encoding="utf-8", errors="replace")
        pages = self.parse_to_pages(content, doc_name)

        all_chunks: list[Chunk] = []
        chunk_idx = 0
        for page in pages:
            chunks = self.chunk_page(page, start_index=chunk_idx)
            all_chunks.extend(chunks)
            chunk_idx += len(chunks)

        return all_chunks

