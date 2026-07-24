"""Run the REST API with uvicorn: ``python -m synology_rag.api``."""

from __future__ import annotations

import uvicorn

from synology_rag.config import Settings
from synology_rag.observability.logging import configure_logging


def main() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, json_logs=True)
    if not settings.enable_rest_api:
        raise SystemExit("ENABLE_REST_API is false; refusing to start the REST API.")
    uvicorn.run(
        "synology_rag.api.app:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.bind_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
