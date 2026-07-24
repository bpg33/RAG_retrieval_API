"""Deduplication.

Removes noise without discarding genuinely distinct evidence:

* exact duplicate ``(collection, chunk_id)``;
* identical passage text returned from multiple records;
* one passage fully contained in another from the *same document* (overlap that
  adds no context);
* superseded document versions, *only* when a reliable active/latest flag is
  mapped and the same document also has an active passage.

Distinct passages from the same document are preserved.
"""

from __future__ import annotations

import re
from collections import defaultdict

from synology_rag.retrieval.candidate import Candidate

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    if len(candidates) <= 1:
        return list(candidates)

    # Process best-first so the highest-scoring representative survives.
    ordered = sorted(candidates, key=lambda c: c.chunk.score, reverse=True)

    seen_ids: set[tuple[str, str]] = set()
    seen_text: set[str] = set()
    kept: list[Candidate] = []
    for cand in ordered:
        key = (cand.chunk.collection, cand.chunk.chunk_id)
        if key in seen_ids:
            continue
        norm = _norm(cand.chunk.text)
        if norm and norm in seen_text:
            continue
        seen_ids.add(key)
        if norm:
            seen_text.add(norm)
        kept.append(cand)

    kept = _drop_contained(kept)
    kept = _drop_superseded(kept)
    return kept


def _drop_contained(candidates: list[Candidate]) -> list[Candidate]:
    """Drop a passage fully contained in a longer one from the same document."""
    by_doc: dict[str, list[Candidate]] = defaultdict(list)
    for cand in candidates:
        by_doc[cand.chunk.document_id].append(cand)

    to_remove: set[int] = set()
    for group in by_doc.values():
        if len(group) < 2:
            continue
        norms = [(_norm(c.chunk.text), c) for c in group]
        for i, (ni, ci) in enumerate(norms):
            if not ni or id(ci) in to_remove:
                continue
            for j, (nj, cj) in enumerate(norms):
                if i == j or not nj or id(cj) in to_remove:
                    continue
                if len(nj) < len(ni) and nj in ni:
                    to_remove.add(id(cj))
    return [c for c in candidates if id(c) not in to_remove]


def _drop_superseded(candidates: list[Candidate]) -> list[Candidate]:
    """Drop inactive versions when the same document has an active passage."""
    by_doc: dict[str, list[Candidate]] = defaultdict(list)
    for cand in candidates:
        by_doc[cand.chunk.document_id].append(cand)

    remove: set[int] = set()
    for group in by_doc.values():
        has_active = any(c.active is True for c in group)
        if not has_active:
            continue
        for c in group:
            if c.active is False:
                remove.add(id(c))
    return [c for c in candidates if id(c) not in remove]
