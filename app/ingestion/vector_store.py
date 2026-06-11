from __future__ import annotations

import os
from collections.abc import Iterable

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from app.ingestion.embedder import DEFAULT_DENSE_DIM
from app.ingestion.models import DocumentChunk

load_dotenv()

def qdrant_url() -> str:
    return os.getenv("QDRANT_URL", "http://localhost:6333")

COLLECTION = os.getenv("QDRANT_COLLECTION", "wcag_criteria")

FILTERABLE_PAYLOAD_FIELDS = [
    "doc_type",
    "criterion_id",
    "level",
    "principle",
    "guideline",
    "technique_id",
    "technology",
    "wcag_version",
]


def batched(items: list[DocumentChunk], batch_size: int) -> Iterable[list[DocumentChunk]]:
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


class QdrantVectorStore:
    def __init__(self, dense_dim: int = DEFAULT_DENSE_DIM) -> None:
        self.client = QdrantClient(url=qdrant_url())
        self.collection = COLLECTION
        self.dense_dim = dense_dim

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    "dense": VectorParams(size=self.dense_dim, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
                },
            )

        for field in FILTERABLE_PAYLOAD_FIELDS:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Qdrant raises if an index already exists. Existing indexes are fine.
                pass

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[tuple[list[int], list[float]]],
    ) -> None:
        points: list[PointStruct] = []
        for chunk, dense_vector, (sparse_indices, sparse_values) in zip(
            chunks,
            dense_vectors,
            sparse_vectors,
            strict=True,
        ):
            points.append(
                PointStruct(
                    id=chunk.id,
                    vector={
                        "dense": dense_vector,
                        "sparse": {
                            "indices": sparse_indices,
                            "values": sparse_values,
                        },
                    },
                    payload=chunk.payload,
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection, points=points)
