import asyncio
import csv
import hashlib
from pathlib import Path
import urllib.request
import json
import httpx

DATA_DIR = Path("data/docs")
MANIFEST_PATH = Path("data/DATASET_MANIFEST.csv")
REPO_TREE_URL = "https://api.github.com/repos/vercel/next.js/git/trees/canary?recursive=1"
RAW_BASE_URL = "https://raw.githubusercontent.com/vercel/next.js/canary/"


async def download_file(client: httpx.AsyncClient, file_path: str, semaphore: asyncio.Semaphore) -> dict | None:
    async with semaphore:
        url = RAW_BASE_URL + file_path
        try:
            resp = await client.get(url, timeout=20.0)
            if resp.status_code == 200:
                content = resp.content
                out_path = DATA_DIR / file_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(content)
                sha = hashlib.sha256(content).hexdigest()
                return {
                    "path": f"nextjs-docs/{file_path}",
                    "source_url": url,
                    "commit": "canary",
                    "bytes": str(len(content)),
                    "sha256": sha,
                    "collected_on": "2026-11-07",
                    "license": "MIT (repository license.md)",
                }
            print(f"Failed to fetch {file_path}: {resp.status_code}")
        except Exception as exc:
            print(f"Error fetching {file_path}: {exc}")
        return None


async def collect_documents(target_count: int = 520) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Fetching repository tree from GitHub...")
    req = urllib.request.Request(REPO_TREE_URL, headers={"User-Agent": "HackDesk/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    tree = data.get("tree", [])
    # Prioritize docs/ files, then examples/
    docs_files = [
        item["path"]
        for item in tree
        if item["type"] == "blob"
        and item["path"].startswith("docs/")
        and item["path"].endswith((".md", ".mdx"))
    ]
    examples_files = [
        item["path"]
        for item in tree
        if item["type"] == "blob"
        and item["path"].startswith("examples/")
        and item["path"].endswith("README.md")
    ]
    packages_files = [
        item["path"]
        for item in tree
        if item["type"] == "blob"
        and item["path"].startswith("packages/")
        and item["path"].endswith(".md")
    ]

    selected_files = docs_files + examples_files + packages_files
    selected_files = selected_files[:target_count]
    print(f"Selected {len(selected_files)} documentation files to download (target: >= {target_count}).")

    semaphore = asyncio.Semaphore(25)
    records = []
    async with httpx.AsyncClient() as client:
        tasks = [download_file(client, f, semaphore) for f in selected_files]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r:
                records.append(r)

    print(f"Successfully downloaded {len(records)} files to {DATA_DIR}.")

    # Write manifest
    if records:
        with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["path", "source_url", "commit", "bytes", "sha256", "collected_on", "license"],
            )
            writer.writeheader()
            writer.writerows(records)
        print(f"Updated manifest at {MANIFEST_PATH} with {len(records)} entries.")


if __name__ == "__main__":
    asyncio.run(collect_documents())

