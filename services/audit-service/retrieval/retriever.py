from __future__ import annotations

from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    Prefetch,
    SparseVector,
)

from retrieval.embedder import EmbeddingProvider
from retrieval.vector_store import QdrantVectorStore


class HybridRetriever:
    def __init__(self) -> None:
        self.embedder = EmbeddingProvider()
        self.vector_store = QdrantVectorStore(dense_dim=self.embedder.dense_dim)
        self.client = self.vector_store.client
        self.collection = self.vector_store.collection

    @staticmethod
    def _match_any(key: str, values: list[str] | str | None) -> FieldCondition | None:
        if not values:
            return None
        normalized = values if isinstance(values, list) else [values]
        return FieldCondition(key=key, match=MatchAny(any=normalized))

    def _build_filter(
        self,
        *,
        level_filter: list[str] | None = None,
        principle_filter: str | None = None,
        doc_type_filter: list[str] | None = None,
        criterion_id_filter: str | None = None,
        technology_filter: list[str] | None = None,
    ) -> Filter | None:
        conditions = [
            self._match_any("level", level_filter),
            self._match_any("principle", principle_filter),
            self._match_any("doc_type", doc_type_filter),
            self._match_any("criterion_id", criterion_id_filter),
            self._match_any("technology", technology_filter),
        ]
        must = [condition for condition in conditions if condition is not None]
        return Filter(must=must) if must else None

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        level_filter: list[str] | None = None,
        principle_filter: str | None = None,
        doc_type_filter: list[str] | None = None,
        criterion_id_filter: str | None = None,
        technology_filter: list[str] | None = None,
    ) -> list[dict]:
        """Hybrid dense+sparse retrieval fused with Reciprocal Rank Fusion."""
        dense_vec = self.embedder.embed_dense([query])[0]
        sparse_indices, sparse_values = self.embedder.embed_sparse([query])[0]
        sparse_vec = SparseVector(indices=sparse_indices, values=sparse_values)
        payload_filter = self._build_filter(
            level_filter=level_filter,
            principle_filter=principle_filter,
            doc_type_filter=doc_type_filter,
            criterion_id_filter=criterion_id_filter,
            technology_filter=technology_filter,
        )

        results = self.client.query_points(
            collection_name=self.collection,
            prefetch=[
                Prefetch(
                    query=dense_vec,
                    using="dense",
                    filter=payload_filter,
                    limit=max(top_k * 4, top_k),
                ),
                Prefetch(
                    query=sparse_vec,
                    using="sparse",
                    filter=payload_filter,
                    limit=max(top_k * 4, top_k),
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        formatted: list[dict] = []
        for point in results.points:
            payload = point.payload or {}
            formatted.append(
                {
                    "score": point.score,
                    "doc_type": payload.get("doc_type"),
                    "title": payload.get("title"),
                    "criterion_id": payload.get("criterion_id"),
                    "level": payload.get("level"),
                    "principle": payload.get("principle"),
                    "guideline": payload.get("guideline"),
                    "technique_id": payload.get("technique_id"),
                    "technology": payload.get("technology"),
                    "text": payload.get("text", ""),
                    "source_url": payload.get("source_url"),
                    "url": payload.get("source_url"),
                    "techniques": payload.get("related_urls", []),
                    "related_urls": payload.get("related_urls", []),
                    "tags": payload.get("tags", []),
                }
            )
        return formatted


_default_retriever: HybridRetriever | None = None


def retrieve(
    query: str,
    top_k: int = 5,
    level_filter: list[str] | None = None,
    principle_filter: str | None = None,
    doc_type_filter: list[str] | None = None,
    criterion_id_filter: str | None = None,
    technology_filter: list[str] | None = None,
) -> list[dict]:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = HybridRetriever()
    return _default_retriever.retrieve(
        query=query,
        top_k=top_k,
        level_filter=level_filter,
        principle_filter=principle_filter,
        doc_type_filter=doc_type_filter,
        criterion_id_filter=criterion_id_filter,
        technology_filter=technology_filter,
    )
