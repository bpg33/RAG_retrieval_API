#!/usr/bin/env python3
"""Export the REST API OpenAPI schema to docs/openapi.json (no services needed)."""

from __future__ import annotations

import json

import _bootstrap
from synology_rag.api.app import create_app


def main() -> int:
    app = create_app()
    schema = app.openapi()
    out = _bootstrap.ROOT / "docs" / "openapi.json"
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
