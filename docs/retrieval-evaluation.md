# Retrieval evaluation

## Purpose

Measure retrieval quality and latency, establish a baseline, and prevent
regressions. Every retrieval change must be evaluated against a benchmark and
enabled only if it improves measured quality (or fixes a documented defect
without materially reducing quality).

## Two benchmark sets

1. **In-repo regression set** (`tests/retrieval_quality/benchmark.jsonl`) — runs
   against the deterministic fake corpus in CI via
   `tests/retrieval_quality/test_benchmark.py`. It guards the pipeline logic
   (recall/MRR/citations) without confidential data.
2. **Real benchmark set** — built against your actual index with
   `scripts/benchmark.py`. **Not committed** if it would expose confidential
   content (store queries/expected ids only, or keep it outside version control).

## Building the real benchmark set (≥30 questions)

Create a JSONL file, one object per line:

```json
{"id": "q1", "query": "…", "expected_document_ids": ["doc-78"]}
{"id": "q2", "query": "…", "expected_document_ids": []}
```

Include, per §17.4:
- Names, codes, dates, and acronyms.
- Cases with **no answer** in the index (empty `expected_document_ids`).
- Cases with duplicate/superseded document versions.
- Cases requiring neighbouring chunks.
- Cases spanning PDFs, PowerPoints, Word documents, and other indexed types.

## Running

```bash
python scripts/benchmark.py --dataset path/to/benchmark.jsonl --k 10
```

Writes a JSON report to `benchmark-results/` and prints a summary.

## Metrics

- **Recall@K** — fraction of expected documents retrieved (answerable cases).
- **Precision@K** — fraction of retrieved documents that were expected.
- **MRR** — mean reciprocal rank of the first expected document.
- **Citation correctness** — expected document appears in the citations.
- **Empty-result correctness** — no-answer questions return no results.
- **Latency** — median / p95 / max over the run.

## Performance targets

Initial local-network targets (record actuals; these are goals, not assumptions):

| Stage | Target (median) |
|---|---|
| API overhead (excl. embedding/DB) | < 50 ms |
| Qdrant search | < 300 ms |
| PostgreSQL enrichment | < 150 ms |
| Full pipeline | < 1.5 s |
| p95 (normal queries) | < 3 s |
| Startup | < 10 s |

## Recorded baseline

> Fill in after your first real run.

| Date | Dataset size | Recall@10 | Precision@10 | MRR | Citation correctness | Empty correctness | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| _____ | _____ | _____ | _____ | _____ | _____ | _____ | _____ | _____ |

## Regression policy

- Run the in-repo set on every change (`make test`).
- Run the real set before enabling any retrieval enhancement.
- Reject changes that reduce recall/MRR/citation correctness unless they fix a
  documented defect and overall quality is not materially reduced.

## In-repo baseline (fake corpus)

The committed regression test asserts, over the fake corpus:
`Recall@5 == 1.0`, `MRR ≥ 0.9`, `citation correctness == 1.0`. These validate the
pipeline, not real-world quality — that comes from your real benchmark set.
