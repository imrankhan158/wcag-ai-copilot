from __future__ import annotations

import hashlib
import json
import logging
import os
from functools import cached_property

from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from openai import OpenAI

load_dotenv()
logger = logging.getLogger("audit-service.embedder")

DEFAULT_DENSE_MODEL = "text-embedding-3-small"
DEFAULT_DENSE_DIM = 1536
DEFAULT_SPARSE_MODEL = "prithivida/Splade_PP_en_v1"

# Module-level Redis reference (synchronous redis client), set by main.py at startup
_redis_client = None

def set_redis_client(redis_instance):
    global _redis_client
    _redis_client = redis_instance

EMBEDDING_CACHE_TTL = 7 * 24 * 3600  # 7 days

class EmbeddingProvider:
    """Dense OpenAI-compatible embeddings plus FastEmbed sparse embeddings with Redis caching."""

    def __init__(self) -> None:
        api_key = (
            os.getenv("EMBEDDING_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("NVIDIA_API_KEY")
        )
        base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        if not base_url and os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            base_url = "https://integrate.api.nvidia.com/v1"

        self.dense_model = os.getenv("DENSE_EMBEDDING_MODEL", DEFAULT_DENSE_MODEL)
        self.dense_dim = int(os.getenv("DENSE_EMBEDDING_DIM", str(DEFAULT_DENSE_DIM)))
        self.sparse_model_name = os.getenv("SPARSE_EMBEDDING_MODEL", DEFAULT_SPARSE_MODEL)
        self.openai_client = OpenAI(api_key=api_key, base_url=base_url)

    @cached_property
    def sparse_model(self) -> SparseTextEmbedding:
        return SparseTextEmbedding(model_name=self.sparse_model_name)

    def _cache_key(self, text: str) -> str:
        return f"emb:dense:{hashlib.sha256(text.encode()).hexdigest()}"

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Embed with Redis cache for dense vectors."""
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        # Try cache lookup synchronously
        if _redis_client is not None:
            for i, text in enumerate(texts):
                cache_key = self._cache_key(text)
                try:
                    cached = _redis_client.get(cache_key)
                    if cached:
                        results[i] = json.loads(cached)
                        logger.debug(f"Embedding cache HIT for text hash {cache_key[-8:]}")
                    else:
                        uncached_indices.append(i)
                        uncached_texts.append(text)
                except Exception as e:
                    logger.warning(f"Embedding cache lookup failed: {e}")
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = list(texts)

        # Fetch uncached embeddings from API
        if uncached_texts:
            response = self.openai_client.embeddings.create(
                model=self.dense_model,
                input=uncached_texts,
            )
            fresh_embeddings = [item.embedding for item in response.data]

            for idx, embedding in zip(uncached_indices, fresh_embeddings):
                results[idx] = embedding

            # Write cache synchronously
            if _redis_client is not None:
                for text, embedding in zip(uncached_texts, fresh_embeddings):
                    cache_key = self._cache_key(text)
                    try:
                        _redis_client.set(cache_key, json.dumps(embedding), ex=EMBEDDING_CACHE_TTL)
                    except Exception as e:
                        logger.warning(f"Failed to cache embedding: {e}")

        return results

    def embed_sparse(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        sparse_embeddings = list(self.sparse_model.embed(texts))
        return [
            (embedding.indices.tolist(), embedding.values.tolist())
            for embedding in sparse_embeddings
        ]
