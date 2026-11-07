# Dataset

## Collection status

Collected **520 Next.js documentation and guide pages** from the [vercel/next.js repository](https://github.com/vercel/next.js) (canary branch / commit snapshot). The dataset covers:
- Next.js App Router core documentation (`docs/01-app/`)
- Next.js Pages Router documentation (`docs/02-pages/`)
- Architectural overviews and guides (`docs/03-architecture/`, `docs/guides/`)
- Verified Next.js example configurations and implementations (`examples/*/README.md`)

When parsed and segmented using `MarkdownDocumentParser`, the dataset produces:
- **520** source documentation documents
- **3,365** logical document pages (preserving page numbering 1, 2, ...)
- **6,781** semantic vector chunks with preserved heading breadcrumbs and page citations

The complete source file list, raw GitHub URLs, byte sizes, and SHA-256 checksums are recorded in [data/DATASET_MANIFEST.csv](data/DATASET_MANIFEST.csv). Downloaded documentation files are stored under `data/docs/` and indexed in pgvector / SQLite vector store. A three-page sample is committed in `data/sample/`; its [README](data/sample/README.md) records provenance, and [LICENSE.md](data/sample/LICENSE.md) contains the repository's MIT license.

| Source | Collected files | Logical pages | Chunks | Licence | Sample |
|---|---:|---:|---:|---|---|
| [Next.js official repository](https://github.com/vercel/next.js) | 520 | 3,365 | 6,781 | [MIT](https://github.com/vercel/next.js/blob/canary/license.md) | MDX pages in `data/sample/` |
