"""Conservative Phase 1 query normalisation.

Phase 1 deliberately does *not* rewrite meaning: no LLM expansion, no stemming,
no synonym injection. It only trims and collapses whitespace so that names,
codes, acronyms, and numbers are preserved exactly. Both the original and
normalised query are kept in memory; only the normalised form is used for
embedding, and neither is logged unless content logging is explicitly enabled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")


@dataclass(slots=True)
class NormalisedQuery:
    original: str
    normalised: str


def normalise_query(query: str) -> NormalisedQuery:
    collapsed = _WHITESPACE.sub(" ", query).strip()
    return NormalisedQuery(original=query, normalised=collapsed)
