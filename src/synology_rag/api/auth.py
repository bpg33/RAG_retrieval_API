"""Local API-key authentication.

When ``LOCAL_API_KEY`` is set, every non-health request must present a matching
``X-API-Key`` header. Comparison is constant-time. When the key is unset (pure
localhost development), authentication is disabled and a warning is logged at
startup.
"""

from __future__ import annotations

import secrets

from fastapi import Header, Request

from synology_rag.domain.errors import AuthenticationError


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    settings = request.app.state.container.settings
    expected = settings.local_api_key
    if not expected:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise AuthenticationError("A valid X-API-Key header is required.")
