import asyncio
import logging
from pathlib import Path

from sqlalchemy.engine import Engine

from app.config import Settings, get_settings
from app.main import create_usage_engine
from app.parser import MarkdownDocumentParser
from app.vector_store import VectorStore, generate_embedding

logger = logging.getLogger(__name__)


async def index_directory(
    data_dir: Path | str,
    engine: Engine,
    settings: Settings,
    batch_size: int = 50,
) -> dict[str, int]:
    """Parse, embed, and index all markdown/mdx files from a directory into the vector store."""
    path = Path(data_dir)
    if not path.exists():
        logger.warning("Directory %s does not exist.", data_dir)
        return {"documents": 0, "pages": 0, "chunks": 0}

    parser = MarkdownDocumentParser()
    vector_store = VectorStore(engine, settings)
    vector_store.init_db()

    # Find all MD and MDX files
    files = list(path.rglob("*.mdx")) + list(path.rglob("*.md"))
    # Filter out git internal files or license/readme if not desired, or keep all
    files = [f for f in files if not f.name.startswith(".")]

    total_pages = 0
    total_chunks = 0
    all_chunks = []

    for file_path in files:
        chunks = parser.parse_file(file_path, base_dir=path)
        if chunks:
            pages_in_doc = max(c.page for c in chunks)
            total_pages += pages_in_doc
            total_chunks += len(chunks)
            all_chunks.extend(chunks)

    # Embed and add in batches
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        # Generate embeddings
        emb_tasks = [generate_embedding(c.content, settings) for c in batch]
        embeddings = await asyncio.gather(*emb_tasks)
        vector_store.add_chunks(batch, embeddings)

    return {
        "documents": len(files),
        "pages": total_pages,
        "chunks": total_chunks,
    }


def run_indexer():
    settings = get_settings()
    engine = create_usage_engine(settings.database_url)
    data_path = Path(settings.docs_data_path)
    if not data_path.exists() or not list(data_path.rglob("*.md*")):
        data_path = Path("data")

    print(f"Indexing documentation from {data_path} into {settings.database_url}...")
    stats = asyncio.run(index_directory(data_path, engine, settings))
    print(f"Indexing complete! Stats: {stats}")


if __name__ == "__main__":
    run_indexer()
