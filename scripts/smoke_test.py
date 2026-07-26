#!/usr/bin/env python3
"""End-to-end smoke test against the configured services.

Builds the real retrieval service from your ``.env``, runs one search, and
prints the top results and citations. Read-only.

Usage:
    python scripts/smoke_test.py --query "your question" --limit 5
"""

from __future__ import annotations

import argparse
import asyncio

import _bootstrap

_bootstrap.load_env()

from synology_rag.container import build_container  # noqa: E402
from synology_rag.domain.models import SearchRequest  # noqa: E402
from synology_rag.observability.logging import configure_logging  # noqa: E402


async def run(query: str, limit: int) -> int:
    container = build_container()
    configure_logging(level=container.settings.log_level, json_logs=False)
    await container.startup()
    try:
        response = await container.service.search(SearchRequest(query=query, limit=limit))
    finally:
        await container.shutdown()

    print(f"\nsearch_id={response.search_id}  elapsed_ms={response.elapsed_ms}")
    if response.warnings:
        print("warnings:")
        for warning in response.warnings:
            print(f"  - {warning}")
    print(f"\n{len(response.results)} result(s):")
    for chunk in response.results:
        marker = " (neighbour)" if chunk.is_neighbour else ""
        source = chunk.filename or chunk.title or chunk.document_id
        snippet = chunk.text[:160].replace("\n", " ")
        print(f"  [{chunk.rank}] {source} score={chunk.score:.4f}{marker}")
        print(f"      {snippet}…")
    print("\ncitations:")
    for citation in response.citations:
        loc = f" ({citation.locator})" if citation.locator else ""
        print(f"  {citation.citation_id}: {citation.display_name}{loc}")
    return 0 if response.results else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval smoke test")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    return asyncio.run(run(args.query, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
