from __future__ import annotations

import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from retrieval.embedder import DEFAULT_DENSE_DIM

load_dotenv()

def qdrant_url() -> str:
    return os.getenv("QDRANT_URL", "http://localhost:6333")

COLLECTION = os.getenv("QDRANT_COLLECTION", "wcag_criteria")

class QdrantVectorStore:
    def __init__(self, dense_dim: int = DEFAULT_DENSE_DIM) -> None:
        self.client = QdrantClient(url=qdrant_url())
        self.collection = COLLECTION
        self.dense_dim = dense_dim
