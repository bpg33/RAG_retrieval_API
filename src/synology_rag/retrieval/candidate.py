"""Internal candidate wrapper used across pipeline stages.

Carries the public :class:`RetrievedChunk` plus the private ``sequence`` value
needed for neighbour expansion, without polluting the public domain model.
"""

from __future__ import annotations

from dataclasses import dataclass

from synology_rag.domain.models import RetrievedChunk


@dataclass(slots=True)
class Candidate:
    chunk: RetrievedChunk
    sequence: int | None = None
    # Latest/active-version flag from the payload, or None when not mapped.
    active: bool | None = None
