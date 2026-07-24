#!/usr/bin/env python3
"""Retrieval-quality and latency benchmark.

Runs a benchmark set (JSONL) against the configured retrieval service and
reports Recall@K, Precision@K, MRR, citation correctness, empty-result
correctness, and latency percentiles. Writes a JSON report to
``benchmark-results/``.

Benchmark line format (one JSON object per line):
    {"id": "q1", "query": "...", "expected_document_ids": ["doc-78"]}
    {"id": "q2", "query": "...", "expected_document_ids": []}   # no-answer case

Usage:
    python scripts/benchmark.py --dataset tests/retrieval_quality/benchmark.jsonl --k 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import _bootstrap

_bootstrap.load_env()

from synology_rag.container import build_container  # noqa: E402
from synology_rag.domain.models import SearchRequest  # noqa: E402
from synology_rag.observability.logging import configure_logging  # noqa: E402
from synology_rag.retrieval.service import RetrievalService  # noqa: E402


def load_dataset(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(json.loads(line))
    return cases


async def evaluate(
    service: RetrievalService, cases: list[dict[str, object]], k: int
) -> dict[str, object]:
    recalls: list[float] = []
    precisions: list[float] = []
    rr: list[float] = []
    citation_hits: list[float] = []
    empty_correct: list[float] = []
    latencies: list[float] = []

    for case in cases:
        query = str(case["query"])
        expected = set(map(str, case.get("expected_document_ids", [])))  # type: ignore[arg-type]

        start = time.perf_counter()
        response = await service.search(
            SearchRequest(query=query, limit=k, include_neighbours=False)
        )
        latencies.append((time.perf_counter() - start) * 1000)

        returned = [c.document_id for c in response.results]
        returned_set = set(returned)

        if not expected:
            empty_correct.append(1.0 if not returned else 0.0)
            continue

        hits = expected & returned_set
        recalls.append(len(hits) / len(expected))
        precisions.append((len(hits) / len(returned)) if returned else 0.0)
        rr.append(_reciprocal_rank(returned, expected))
        cited = {c.document_id for c in response.citations}
        citation_hits.append(1.0 if expected & cited else 0.0)

    return {
        "cases": len(cases),
        "answerable_cases": len(recalls),
        "no_answer_cases": len(empty_correct),
        "recall_at_k": _mean(recalls),
        "precision_at_k": _mean(precisions),
        "mrr": _mean(rr),
        "citation_correctness": _mean(citation_hits),
        "empty_result_correctness": _mean(empty_correct),
        "latency_ms": {
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "p95": round(_percentile(latencies, 95), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
    }


def _reciprocal_rank(returned: list[str], expected: set[str]) -> float:
    for index, doc_id in enumerate(returned, start=1):
        if doc_id in expected:
            return 1.0 / index
    return 0.0


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


async def run(dataset: Path, k: int) -> int:
    cases = load_dataset(dataset)
    container = build_container()
    configure_logging(level=container.settings.log_level, json_logs=False)
    await container.startup()
    try:
        report = await evaluate(container.service, cases, k)
    finally:
        await container.shutdown()

    report["k"] = k
    report["dataset"] = str(dataset)
    report["generated_at"] = datetime.now(tz=UTC).isoformat()

    out_dir = _bootstrap.ROOT / "benchmark-results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"benchmark-{int(time.time())}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval benchmark")
    parser.add_argument(
        "--dataset", type=Path, default=_bootstrap.ROOT / "tests/retrieval_quality/benchmark.jsonl"
    )
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    return asyncio.run(run(args.dataset, args.k))


if __name__ == "__main__":
    raise SystemExit(main())
