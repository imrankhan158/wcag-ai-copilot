from __future__ import annotations

import os
from functools import cached_property

from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from openai import OpenAI

load_dotenv()

DEFAULT_DENSE_MODEL = "text-embedding-3-small"
DEFAULT_DENSE_DIM = 1536
DEFAULT_SPARSE_MODEL = "prithivida/Splade_PP_en_v1"


class EmbeddingProvider:
    """Dense OpenAI-compatible embeddings plus FastEmbed sparse embeddings."""

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

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        response = self.openai_client.embeddings.create(
            model=self.dense_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def embed_sparse(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        sparse_embeddings = list(self.sparse_model.embed(texts))
        return [
            (embedding.indices.tolist(), embedding.values.tolist())
            for embedding in sparse_embeddings
        ]
