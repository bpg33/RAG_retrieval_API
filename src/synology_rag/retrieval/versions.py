"""Opt-in collapsing of near-duplicate document versions.

Some corpora contain several saved versions of the same document as distinct
files (e.g. ``… v2.pptx`` … ``… v6.pptx``). Because their content is nearly
identical they crowd the top results. When enabled, this stage keeps one
representative per version-family across *different* documents - preferring the
most recently modified (else the highest score) - and preserves the family's
best score so it keeps its ranking position.

Two signals mark results as the same family:
* a normalised filename family match (trailing version markers stripped), or
* very high normalised-text similarity (Jaccard), guarded by a minimum token
  count so short boilerplate is never collapsed.

Same-document chunks are never collapsed here (that is deduplication's job); this
only merges across documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from synology_rag.retrieval.candidate import Candidate

_WORD = re.compile(r"\w+", re.UNICODE)
# Trailing version markers: " v3", "_v3", "-v3", "(2)", " copy", " final", " draft".
_VERSION_SUFFIX = re.compile(
    r"[ _\-]*(v\d+|\(\d+\)|copy|final|draft)\s*$", re.IGNORECASE
)
_MIN_TEXT_TOKENS = 8


def _family_key(filename: str | None) -> str:
    if not filename:
        return ""
    name = filename.rsplit(".", 1)[0].strip().lower()
    previous = None
    while name and name != previous:
        previous = name
        name = _VERSION_SUFFIX.sub("", name).strip()
    return name


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _prefer_replacement(new: Candidate, current: Candidate) -> bool:
    """Prefer the most recently modified version as the representative."""
    new_dt = new.chunk.modified_at
    cur_dt = current.chunk.modified_at
    if new_dt is not None and cur_dt is not None:
        return new_dt > cur_dt
    # Without dates, keep the higher-ranked (earlier) candidate.
    return False


@dataclass
class _Group:
    rep: Candidate
    family: str
    tokens: set[str]
    best_score: float = field(default=0.0)


def collapse_versions(
    candidates: list[Candidate], *, similarity_threshold: float
) -> tuple[list[Candidate], int]:
    """Collapse near-duplicate versions. Returns (kept, collapsed_count)."""
    groups: list[_Group] = []
    collapsed = 0

    for cand in candidates:
        family = _family_key(cand.chunk.filename)
        tokens = _tokens(cand.chunk.text)
        target: _Group | None = None
        for group in groups:
            if cand.chunk.document_id == group.rep.chunk.document_id:
                continue  # same document is not a cross-version duplicate
            same_family = bool(family) and family == group.family
            text_dup = (
                len(tokens) >= _MIN_TEXT_TOKENS
                and len(group.tokens) >= _MIN_TEXT_TOKENS
                and _jaccard(tokens, group.tokens) >= similarity_threshold
            )
            if same_family or text_dup:
                target = group
                break

        if target is None:
            groups.append(
                _Group(rep=cand, family=family, tokens=tokens, best_score=cand.chunk.score)
            )
            continue

        collapsed += 1
        target.best_score = max(target.best_score, cand.chunk.score)
        if _prefer_replacement(cand, target.rep):
            target.rep = cand

    kept: list[Candidate] = []
    for group in groups:
        group.rep.chunk.score = group.best_score  # keep the family's best rank
        kept.append(group.rep)
    kept.sort(key=lambda c: c.chunk.score, reverse=True)
    return kept, collapsed
