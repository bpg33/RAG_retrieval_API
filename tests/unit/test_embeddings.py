"""Unit tests for embedding providers."""

from __future__ import annotations

import httpx
import pytest

from synology_rag.adapters.embedding_provider import (
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from synology_rag.domain.errors import EmbeddingIncompatibleError, EmbeddingUnavailableError


async def test_fake_embedder_is_deterministic() -> None:
    provider = FakeEmbeddingProvider(dimensions=32)
    a = await provider.embed_query("hello world")
    b = await provider.embed_query("hello world")
    assert a == b
    assert len(a) == 32


async def test_fake_embedder_shared_tokens_are_more_similar() -> None:
    provider = FakeEmbeddingProvider(dimensions=128, normalise=True)
    import math

    def cos(x: list[float], y: list[float]) -> float:
        return sum(a * b for a, b in zip(x, y, strict=False))

    base = await provider.embed_query("asset tagging implementation risks")
    near = await provider.embed_query("asset tagging risks")
    far = await provider.embed_query("banana smoothie recipe")
    assert cos(base, near) > cos(base, far)
    assert math.isclose(sum(v * v for v in base), 1.0, rel_tol=1e-6)


def _provider_with(handler) -> OpenAICompatibleEmbeddingProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://embed.test/v1")
    return OpenAICompatibleEmbeddingProvider(
        base_url="http://embed.test/v1",
        model="test-model",
        dimensions=4,
        api_key=None,
        timeout_seconds=5,
        client=client,
    )


async def test_openai_compatible_parses_embedding() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]})

    provider = _provider_with(handler)
    vector = await provider.embed_query("q")
    assert vector == [0.1, 0.2, 0.3, 0.4]


async def test_dimension_mismatch_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    provider = _provider_with(handler)
    with pytest.raises(EmbeddingIncompatibleError):
        await provider.embed_query("q")


async def test_provider_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = _provider_with(handler)
    with pytest.raises(EmbeddingUnavailableError):
        await provider.embed_query("q")


async def test_transport_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    provider = _provider_with(handler)
    with pytest.raises(EmbeddingUnavailableError):
        await provider.embed_query("q")
