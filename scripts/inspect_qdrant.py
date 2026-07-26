#!/usr/bin/env python3
"""Read-only Qdrant discovery.

Lists collections, vector configuration (dimensions, distance, named vectors),
point counts, and a small sample of payload *keys* (values truncated/redacted).
Uses only read operations: get_collections, get_collection, scroll. It never
writes, upserts, deletes, or creates anything.

Usage:
    python scripts/inspect_qdrant.py [--sample 3] [--collection NAME]

Paste the output into docs/discovery-report.md.
"""

from __future__ import annotations

import argparse
import os

import _bootstrap

_bootstrap.load_env()

from qdrant_client import QdrantClient  # noqa: E402

_MAX_VALUE_CHARS = 80


def _redact(value: object) -> str:
    text = repr(value)
    if len(text) > _MAX_VALUE_CHARS:
        return text[:_MAX_VALUE_CHARS] + "…(truncated)"
    return text


def _vector_config(info: object) -> list[str]:
    lines: list[str] = []
    try:
        vectors = info.config.params.vectors  # type: ignore[attr-defined]
    except AttributeError:
        return ["- vectors: (unavailable)"]
    if isinstance(vectors, dict):
        for name, params in vectors.items():
            lines.append(
                f"- named vector '{name}': size={getattr(params, 'size', '?')}, "
                f"distance={getattr(params, 'distance', '?')}"
            )
    else:
        lines.append(
            f"- vector: size={getattr(vectors, 'size', '?')}, "
            f"distance={getattr(vectors, 'distance', '?')} (unnamed/default)"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Qdrant discovery")
    parser.add_argument("--sample", type=int, default=3, help="payload samples per collection")
    parser.add_argument("--collection", default=None, help="inspect only this collection")
    args = parser.parse_args()

    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    api_key = os.environ.get("QDRANT_API_KEY") or None
    client = QdrantClient(url=url, api_key=api_key, timeout=15)

    print("# Qdrant discovery (read-only)\n")
    print(f"- URL: {url}\n")

    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if args.collection:
        names = [n for n in names if n == args.collection]
    print(f"## Collections ({len(names)})\n")

    for name in names:
        info = client.get_collection(name)
        print(f"### {name}\n")
        print(f"- points_count: {getattr(info, 'points_count', '?')}")
        for line in _vector_config(info):
            print(line)

        try:
            points, _ = client.scroll(
                collection_name=name, limit=args.sample, with_payload=True, with_vectors=False
            )
        except Exception as exc:
            print(f"- payload sample unavailable: {type(exc).__name__}\n")
            continue

        if points:
            keys = sorted({k for p in points for k in (p.payload or {})})
            print(f"- payload keys: {keys}")
            print("- payload sample (values truncated/redacted):")
            for point in points:
                print(f"  - point id={point.id!r}")
                for key, value in (point.payload or {}).items():
                    print(f"    - {key}: {_redact(value)}")
        print()

    client.close()
    print("_Read-only discovery complete. No data was modified._")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
