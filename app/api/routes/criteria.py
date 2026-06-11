from __future__ import annotations

from fastapi import APIRouter, Query

from app.ingestion.vector_store import QdrantVectorStore

router = APIRouter()
store = QdrantVectorStore()
qdrant = store.client
COLLECTION = store.collection


@router.get("/criteria")
async def list_criteria(
    level: str | None = Query(None, description="A, AA, or AAA"),
    principle: str | None = Query(None, description="Perceivable, Operable, etc."),
):
    results, _ = qdrant.scroll(
        collection_name=COLLECTION,
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )

    # Filter for success criteria (those with doc_type success_criterion and a valid criterion_id)
    criteria = [
        r.payload
        for r in results
        if r.payload
        and r.payload.get("doc_type") == "success_criterion"
        and r.payload.get("criterion_id")
    ]

    # Map database keys to frontend expected keys if different (e.g. source_url to url)
    for c in criteria:
        if "url" not in c and "source_url" in c:
            c["url"] = c["source_url"]

    if level:
        criteria = [c for c in criteria if c.get("level") == level]
    if principle:
        criteria = [c for c in criteria if c.get("principle") == principle]

    # Sort criteria numerically by ID (e.g., "1.1.1" -> [1, 1, 1])
    try:
        criteria.sort(key=lambda c: [int(x) for x in c["criterion_id"].split(".")])
    except Exception:
        pass

    return {"criteria": criteria, "total": len(criteria)}
