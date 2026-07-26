"""Context-budget enforcement.

Caps the number of chunks, the characters per chunk, and the total characters
returned. Truncation is always made explicit: the affected chunk's ``truncated``
flag is set, the response is marked truncated, and a warning is emitted.
"""

from __future__ import annotations

from dataclasses import dataclass

from synology_rag.domain.models import RetrievedChunk


@dataclass(slots=True)
class BudgetResult:
    chunks: list[RetrievedChunk]
    truncated: bool
    warnings: list[str]


def apply_context_budget(
    chunks: list[RetrievedChunk],
    *,
    max_total_chunks: int,
    max_total_characters: int,
    max_characters_per_chunk: int,
) -> BudgetResult:
    warnings: list[str] = []
    truncated = False

    if len(chunks) > max_total_chunks:
        warnings.append(
            f"Result set capped at {max_total_chunks} chunks "
            f"(had {len(chunks)})."
        )
        chunks = chunks[:max_total_chunks]
        truncated = True

    kept: list[RetrievedChunk] = []
    used = 0
    dropped_for_budget = False
    for chunk in chunks:
        text = chunk.text
        if max_characters_per_chunk > 0 and len(text) > max_characters_per_chunk:
            text = text[:max_characters_per_chunk]
            chunk.text = text
            chunk.truncated = True
            truncated = True

        remaining = max_total_characters - used
        if remaining <= 0:
            dropped_for_budget = True
            break
        if len(text) > remaining:
            chunk.text = text[:remaining]
            chunk.truncated = True
            truncated = True
            used += remaining
            kept.append(chunk)
            dropped_for_budget = True
            break

        used += len(text)
        kept.append(chunk)

    if dropped_for_budget and len(kept) < len(chunks):
        warnings.append(
            f"Output truncated to the {max_total_characters}-character budget."
        )
        truncated = True

    return BudgetResult(chunks=kept, truncated=truncated, warnings=warnings)
