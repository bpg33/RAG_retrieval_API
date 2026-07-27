"""Unit tests for the bounded retry helper."""

from __future__ import annotations

import pytest

from synology_rag.domain.errors import InvalidRequestError, QdrantUnavailableError
from synology_rag.retrieval.retry import with_retries


async def test_retries_retryable_then_succeeds() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise QdrantUnavailableError("down")  # retryable
        return "ok"

    result = await with_retries(flaky, retries=3, base_delay=0.0)
    assert result == "ok"
    assert calls["n"] == 3


async def test_does_not_retry_non_retryable() -> None:
    calls = {"n": 0}

    async def bad() -> str:
        calls["n"] += 1
        raise InvalidRequestError("nope")  # not retryable

    with pytest.raises(InvalidRequestError):
        await with_retries(bad, retries=3, base_delay=0.0)
    assert calls["n"] == 1


async def test_gives_up_after_max_retries() -> None:
    calls = {"n": 0}

    async def always_down() -> str:
        calls["n"] += 1
        raise QdrantUnavailableError("down")

    with pytest.raises(QdrantUnavailableError):
        await with_retries(always_down, retries=2, base_delay=0.0)
    assert calls["n"] == 3  # initial + 2 retries
