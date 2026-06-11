from __future__ import annotations

import argparse
from collections import Counter, deque

from app.ingestion.chunker import chunk_documents
from app.ingestion.embedder import EmbeddingProvider
from app.ingestion.fetcher import PlaywrightFetcher
from app.ingestion.models import IngestDocument, SourceDefinition
from app.ingestion.parsers.w3c import parse_source
from app.ingestion.source_registry import APG_SOURCE, DEFAULT_SOURCES, canonical_url, source_priority
from app.ingestion.vector_store import QdrantVectorStore, batched

DEFAULT_MAX_PAGES = 250
DEFAULT_BATCH_SIZE = 32


def collect_documents(
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    refresh_cache: bool = False,
    include_apg: bool = False,
) -> list[IngestDocument]:
    fetcher = PlaywrightFetcher(refresh=refresh_cache)
    seed_sources = [*DEFAULT_SOURCES, APG_SOURCE] if include_apg else DEFAULT_SOURCES
    queue: deque[SourceDefinition] = deque(seed_sources)
    seen_sources: set[str] = set()
    documents: list[IngestDocument] = []

    while queue and len(seen_sources) < max_pages:
        source = queue.popleft()
        source_key = canonical_url(source.url)
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        print(f"Fetching [{len(seen_sources)}/{max_pages}] {source.source_type}: {source.url}", flush=True)
        try:
            html = fetcher.fetch(source.url)
            parsed = parse_source(html, source)
        except Exception as exc:
            print(f"  Skipped {source.url}: {exc}", flush=True)
            continue

        documents.extend(parsed.documents)
        discovered_sources = sorted(parsed.discovered_sources, key=source_priority)
        for discovered in discovered_sources:
            if discovered.source_type == "aria_apg" and not include_apg:
                continue
            discovered_key = canonical_url(discovered.url)
            if discovered_key not in seen_sources:
                queue.append(discovered)

        print(f"  Parsed {len(parsed.documents)} docs, queued {len(queue)} sources", flush=True)

    return documents


def ingest(
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    refresh_cache: bool = False,
    dry_run: bool = False,
    include_apg: bool = False,
) -> None:
    documents = collect_documents(max_pages=max_pages, refresh_cache=refresh_cache, include_apg=include_apg)
    chunks = chunk_documents(documents)

    doc_counts = Counter(document.doc_type for document in documents)
    chunk_counts = Counter(chunk.payload.get("doc_type") for chunk in chunks)
    print("\nParsed document counts:", flush=True)
    for doc_type, count in sorted(doc_counts.items()):
        print(f"  {doc_type}: {count}", flush=True)
    print("\nChunk counts:", flush=True)
    for doc_type, count in sorted(chunk_counts.items()):
        print(f"  {doc_type}: {count}", flush=True)
    print(f"\nTotal documents: {len(documents)}", flush=True)
    print(f"Total chunks: {len(chunks)}", flush=True)

    if dry_run:
        print("Dry run complete. No embeddings or Qdrant writes performed.", flush=True)
        return

    embedder = EmbeddingProvider()
    vector_store = QdrantVectorStore(dense_dim=embedder.dense_dim)
    vector_store.ensure_collection()

    for batch_number, chunk_batch in enumerate(batched(chunks, batch_size), start=1):
        texts = [chunk.text for chunk in chunk_batch]
        dense_vectors = embedder.embed_dense(texts)
        sparse_vectors = embedder.embed_sparse(texts)
        vector_store.upsert_chunks(chunk_batch, dense_vectors, sparse_vectors)
        print(f"Upserted batch {batch_number}: {len(chunk_batch)} chunks", flush=True)

    print(f"Ingested {len(chunks)} chunks into Qdrant.", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest official accessibility guidance into Qdrant.")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-apg", action="store_true", help="Also crawl ARIA Authoring Practices Guide pages.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ingest(
        max_pages=args.max_pages,
        batch_size=args.batch_size,
        refresh_cache=args.refresh_cache,
        dry_run=args.dry_run,
        include_apg=args.include_apg,
    )
