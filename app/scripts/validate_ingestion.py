from __future__ import annotations

import argparse
from collections import Counter

from app.retrieval.retriever import retrieve
from app.ingestion.vector_store import QdrantVectorStore


def validate_collection(sample_query: str | None = None) -> None:
    store = QdrantVectorStore()
    info = store.client.get_collection(store.collection)
    print(f"Collection: {store.collection}")
    print(f"Points: {info.points_count}")
    print(f"Vectors: {info.indexed_vectors_count}")

    scroll, _ = store.client.scroll(
        collection_name=store.collection,
        limit=500,
        with_payload=True,
        with_vectors=False,
    )
    doc_types = Counter((point.payload or {}).get("doc_type", "unknown") for point in scroll)
    print("Sample payload doc_type counts:")
    for doc_type, count in sorted(doc_types.items()):
        print(f"  {doc_type}: {count}")

    if sample_query:
        print(f"\nSample retrieval: {sample_query}")
        results = retrieve(sample_query, top_k=5)
        for index, result in enumerate(results, start=1):
            criterion = result.get("criterion_id") or "n/a"
            doc_type = result.get("doc_type") or "n/a"
            title = result.get("title") or "Untitled"
            url = result.get("source_url") or ""
            print(f"{index}. [{doc_type}] {criterion} {title}")
            print(f"   {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Qdrant ingestion output.")
    parser.add_argument("--sample-query", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    validate_collection(sample_query=args.sample_query)
