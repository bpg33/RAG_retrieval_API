"""Phase 1 ranking.

Deliberately simple (the specification warns against inventing a complex scoring
formula before retrieval-quality tests exist):

1. primary vector similarity (score, descending);
2. active/latest-version preference as a tie-breaker where a flag is mapped.

Neighbours are never ranked as independent high-score matches; the service
assigns primary ranks and places neighbours adjacent to their parent result.
"""

from __future__ import annotations

from synology_rag.retrieval.candidate import Candidate


def rank_primary(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (c.chunk.score, 1 if c.active is True else 0),
        reverse=True,
    )
