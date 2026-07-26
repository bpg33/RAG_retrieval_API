"""Process-level runtime setup shared by all entrypoints.

The important piece is the event-loop policy on Windows: async ``psycopg``
(used by the PostgreSQL repository) cannot run on the default
``ProactorEventLoop`` and requires a ``SelectorEventLoop``. Every entrypoint
(REST, MCP, scripts) calls :func:`configure_event_loop` before starting an
event loop so PostgreSQL enrichment works on Windows.
"""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """Select an event loop compatible with async psycopg on Windows.

    No-op on non-Windows platforms.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
