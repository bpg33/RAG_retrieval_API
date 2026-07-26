"""Privacy-conscious audit log.

Records who searched, when, which collections were queried, and which document
ids were returned - never passage text or full user questions. Emitted as
structured log events on a dedicated ``synology_rag.audit`` logger.
"""

from __future__ import annotations

from datetime import UTC, datetime

from synology_rag.observability.logging import get_logger

_audit_log = get_logger("synology_rag.audit")


def record_search(
    *,
    client: str,
    search_id: str,
    collections: list[str],
    document_ids: list[str],
    result_count: int,
    success: bool,
) -> None:
    _audit_log.info(
        "audit.search",
        client=client,
        search_id=search_id,
        timestamp=datetime.now(tz=UTC).isoformat(),
        collections=collections,
        document_ids=sorted(set(document_ids)),
        result_count=result_count,
        success=success,
    )
