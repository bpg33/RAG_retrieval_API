"""Retrieval-quality regression test over the in-repo benchmark set.

Runs the benchmark against the fake corpus and asserts recall/MRR thresholds so
retrieval regressions are caught in CI. The full 30+ question benchmark against
real data is run with scripts/benchmark.py (see docs/retrieval-evaluation.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synology_rag.domain.models import SearchRequest
from synology_rag.retrieval.service import RetrievalService

pytestmark = pytest.mark.retrieval_quality


def _load(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


async def test_benchmark_recall_and_mrr(service: RetrievalService, repo_root: Path) -> None:
    cases = _load(repo_root / "tests/retrieval_quality/benchmark.jsonl")
    assert cases, "benchmark dataset must not be empty"

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    citation_hits: list[float] = []

    for case in cases:
        expected = set(map(str, case["expected_document_ids"]))  # type: ignore[arg-type]
        response = await service.search(
            SearchRequest(query=str(case["query"]), limit=5, include_neighbours=False)
        )
        returned = [c.document_id for c in response.results]
        hits = expected & set(returned)
        recalls.append(len(hits) / len(expected))

        rr = 0.0
        for rank, doc_id in enumerate(returned, start=1):
            if doc_id in expected:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        cited = {c.document_id for c in response.citations}
        citation_hits.append(1.0 if expected & cited else 0.0)

    recall_at_5 = sum(recalls) / len(recalls)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    citation_correctness = sum(citation_hits) / len(citation_hits)

    assert recall_at_5 == 1.0, f"recall@5 regressed to {recall_at_5}"
    assert mrr >= 0.9, f"MRR regressed to {mrr}"
    assert citation_correctness == 1.0
