"""Bounded retry with exponential backoff for transient failures.

Only errors marked ``retryable`` (e.g. a briefly unavailable Qdrant or embedding
service) are retried; validation, authentication, and incompatibility errors are
raised immediately. Retries happen within the overall search timeout enforced by
the service.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from synology_rag.domain.errors import RetrievalError

T = TypeVar("T")


async def with_retries(
    factory: Callable[[], Awaitable[T]], *, retries: int, base_delay: float
) -> T:
    """Await ``factory()``; retry retryable errors up to ``retries`` times.

    ``factory`` must return a fresh awaitable on each call so it can be retried.
    """
    attempt = 0
    while True:
        try:
            return await factory()
        except RetrievalError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
            attempt += 1
