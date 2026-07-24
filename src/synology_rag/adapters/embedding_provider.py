"""Embedding providers.

The query embedding MUST be produced by the same model and dimensions as the
existing index. Two providers are supported:

* ``OpenAICompatibleEmbeddingProvider`` - talks to any OpenAI-compatible
  ``/embeddings`` endpoint (OpenAI, Azure OpenAI, LM Studio, Ollama ``/v1``,
  vLLM, text-embeddings-inference). The dimension of every returned vector is
  checked against the configured value; a mismatch fails closed with
  ``EmbeddingIncompatibleError`` rather than silently searching with an
  incompatible vector.
* ``FakeEmbeddingProvider`` - a deterministic, offline hash embedder used for
  tests and local development only. Never enable in production.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from synology_rag.config import EmbeddingProviderName, Settings
from synology_rag.domain.errors import (
    ConfigurationError,
    EmbeddingIncompatibleError,
    EmbeddingUnavailableError,
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _l2_normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]


class FakeEmbeddingProvider:
    """Deterministic hashing embedder. Shared tokens produce similar vectors.

    This exists so the full pipeline can be exercised without a live embedding
    service. It is NOT semantically meaningful and must never be used against a
    real index.
    """

    def __init__(self, *, dimensions: int, model: str = "fake", normalise: bool = True) -> None:
        self._dimensions = dimensions
        self._model = model
        self._normalise = normalise

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _l2_normalise(vector) if self._normalise else vector

    async def health(self) -> bool:
        return True


class OpenAICompatibleEmbeddingProvider:
    """Query embeddings via an OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: int,
        api_key: str | None,
        timeout_seconds: float,
        normalise: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._normalise = normalise
        self._client = client
        self._owns_client = client is None

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        client = self._get_client()
        try:
            response = await client.post(
                "/embeddings", json={"model": self._model, "input": text}
            )
        except httpx.HTTPError as exc:
            # Redact everything but the exception type; URLs/keys never surface.
            raise EmbeddingUnavailableError(
                "The embedding provider is currently unavailable.",
                internal_detail=f"{type(exc).__name__}",
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise EmbeddingUnavailableError(
                "The embedding provider rejected the credentials.",
                internal_detail=f"http {response.status_code}",
            )
        if response.status_code >= 400:
            raise EmbeddingUnavailableError(
                "The embedding provider returned an error.",
                internal_detail=f"http {response.status_code}",
            )

        vector = self._parse_embedding(response.json())
        if len(vector) != self._dimensions:
            raise EmbeddingIncompatibleError(
                "The embedding model produced vectors of an unexpected size; it does "
                "not match the configured index dimensions.",
                internal_detail=f"expected {self._dimensions}, got {len(vector)}",
            )
        return _l2_normalise(vector) if self._normalise else vector

    @staticmethod
    def _parse_embedding(body: dict[str, Any]) -> list[float]:
        try:
            data = body["data"]
            embedding = data[0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingUnavailableError(
                "The embedding provider returned an unexpected response shape.",
                internal_detail=str(type(exc).__name__),
            ) from exc
        return [float(x) for x in embedding]

    async def health(self) -> bool:
        client = self._get_client()
        try:
            # `/models` is commonly available and non-billable. A 404 means the
            # route is absent but the endpoint is reachable, which is fine.
            response = await client.get("/models")
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


def build_embedding_provider(
    settings: Settings, *, client: httpx.AsyncClient | None = None
) -> FakeEmbeddingProvider | OpenAICompatibleEmbeddingProvider:
    """Construct the configured embedding provider."""
    if settings.embedding_provider == EmbeddingProviderName.FAKE:
        dims = settings.embedding_dimensions or 384
        return FakeEmbeddingProvider(dimensions=dims, normalise=settings.embedding_normalise)

    if settings.embedding_model is None or settings.embedding_dimensions is None:
        raise ConfigurationError(
            "EMBEDDING_MODEL and EMBEDDING_DIMENSIONS are required for the "
            "openai_compatible provider."
        )
    return OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=settings.embedding_api_key,
        timeout_seconds=settings.embedding_timeout_seconds,
        normalise=settings.embedding_normalise,
        client=client,
    )
