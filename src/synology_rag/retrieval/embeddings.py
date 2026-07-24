"""Query embedding stage.

Thin wrapper over the configured :class:`EmbeddingProvider`. The provider is
responsible for using the same model/dimensions as the index and for failing
closed on an incompatible response; this stage exists so the pipeline has a
single, mockable seam for embedding generation.
"""

from __future__ import annotations

from synology_rag.domain.ports import EmbeddingProvider


async def generate_query_embedding(provider: EmbeddingProvider, text: str) -> list[float]:
    return await provider.embed_query(text)
