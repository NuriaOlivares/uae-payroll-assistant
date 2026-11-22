#!/usr/bin/env python3
"""Embed the chunks in data/processed/*.jsonl into a local Chroma index (data/index).

Run from the repo root:  python pipeline/build_index.py
Chroma's default embedding model (a small MiniLM) is downloaded on the first run.
"""
import json
from pathlib import Path

import chromadb

CHUNKS_DIR = Path("data/processed")
INDEX_DIR = "data/index"
COLLECTION = "legal"
BATCH = 100


def load_chunks():
    seen, chunks = set(), []
    for path in sorted(CHUNKS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c["id"] in seen:  # ids must be unique inside one collection
                print(f"WARNING: duplicate id {c['id']} in {path.name}; renaming")
                c["id"] += f"-dup{len(seen)}"
            seen.add(c["id"])
            chunks.append(c)
    return chunks


def to_metadata(c):
    # Chroma metadata values must be str/int/float/bool (no None).
    return {
        "doc_id": c["doc_id"],
        "doc_title": c["doc_title"],
        "jurisdiction": c["jurisdiction"],
        "article": int(c["article"]),
        "clause": c["clause"] or "",
        "title": c["title"] or "",
        "citation": c["citation"],
        "page_start": int(c["page_start"]),
        "source_file": c["source_file"],
    }


def main():
    chunks = load_chunks()
    if not chunks:
        raise SystemExit("No chunks found. Run pipeline/ingest.py first.")
    client = chromadb.PersistentClient(path=INDEX_DIR)
    try:
        client.delete_collection(COLLECTION)  # rebuild from scratch every time
    except Exception:
        pass
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        col.add(ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[to_metadata(c) for c in batch])
    per_doc = {}
    for c in chunks:
        per_doc[c["doc_id"]] = per_doc.get(c["doc_id"], 0) + 1
    print(f"Indexed {col.count()} chunks into {INDEX_DIR}: {per_doc}")


if __name__ == "__main__":
    main()