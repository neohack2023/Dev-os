# DEVOS_RETRIEVAL_ABLATION_01

Status: **accepted benchmark checkpoint / no production retrieval promotion**

## Objective

Implement and validate exactly two DevOS retrieval benchmark arms while leaving production `knowledge_runtime.build_packet()` unchanged:

1. `LEXICAL_V1` — current `knowledge_runtime._score()` behavior and branch-tier policy.
2. `FTS5_BM25_V1` — scope-local SQLite FTS5 BM25 over the same branch-eligible corpus, weighted `(path=3, title=6, section=4, content=1)`.

No embeddings, reranker, reciprocal-rank fusion, or other third arm is part of this checkpoint.

## Implementation

- `runtime/retrieval_ablation.py`
- `contracts/RETRIEVAL_ABLATION.md`
- `tests/test_retrieval_ablation.py`
- `tests/fixtures/retrieval_ablation/benchmark.json`
- `tests/fixtures/retrieval_ablation/host/**`
- `.github/workflows/devos-retrieval-ablation.yml`

The lexical arm imports the current production tokenizer, scorer, branch resolver, and branch-tier implementation directly.

The FTS5 arm uses `fts5-literal-or-v1`: current DevOS tokenization followed by literal quoting of every searchable token and `OR` composition. Raw user query syntax is never passed directly into FTS5 `MATCH`.

The FTS5 corpus is rebuilt ephemerally from only documents admitted by the resolved requested/dependency branch surfaces. This makes candidate formation and BM25 corpus statistics scope-local; sibling documents cannot alter the allowed corpus's ranking statistics.

## Frozen benchmark

Benchmark spec SHA-256:

`71114b32f618df9a3f29b61778c2e216e94fee449c71ab4c580d2674073d9083`

The fixture contains 10 queries:

- 6 development
- 4 holdout
- exact identifiers
- natural-language multi-token lookup
- title weighting
- dependency retrieval
- hyphen/underscore identifiers
- path terms
- sibling decoys
- direct/dependency tier competition
- FTS operator-looking literal data
- expected-empty retrieval

## Exact validated candidate before checkpoint

`279354e23d3079322535ab734f24cff99e231158`

PR: `#2` — `Define DEVOS_RETRIEVAL_ABLATION_01 two-arm benchmark`

GitHub Actions on that exact candidate:

- DevOS Portable Validation — run `34854542726` — **success**
- DevOS GitHub Authority Validation — run `34854542934` — **success**
- DevOS GitHub Policy Validation — run `34854542649` — **success**
- DevOS Retrieval Ablation — run `34854542575` — **success**

Revision-bound benchmark artifact:

- artifact ID: `10351983218`
- artifact digest: `sha256:b1cd6b8519658ea35598a7f5f2619548645d6a34fdbb1c25f0fa21b74a96b97f`
- receipt SHA-256: `884b2d2113dc97af10b3794ae71286200973b5a6611bbb1ecebc83a2cc83d75d`
- projection digest: `e02ab0cfc6bd392fd9acdd4b63a26700435ae54b2628070e4d7275cdf5c37e4d`
- SQLite: `3.45.1`, FTS5 available

## Benchmark result

Both fixed arms produced the same aggregate retrieval result on this fixture:

| Metric | LEXICAL_V1 | FTS5_BM25_V1 |
| --- | ---: | ---: |
| Recall@1 | 0.8888888889 | 0.8888888889 |
| Recall@3 | 1.0 | 1.0 |
| Recall@5 | 1.0 | 1.0 |
| MRR | 1.0 | 1.0 |
| Expected-empty accuracy | 1.0 | 1.0 |
| Scope leakage | 0 | 0 |
| Branch-tier violations | 0 | 0 |
| Missed at top-5 | 0 | 0 |

Holdout results were also tied:

- Recall@1: `0.8333333333`
- Recall@3: `1.0`
- Recall@5: `1.0`
- MRR: `1.0`
- expected-empty accuracy: `1.0`
- scope leakage: `0`
- branch-tier violations: `0`

## Disposition

`FTS5_BM25_V1` is **not promoted into production retrieval** by this checkpoint.

The frozen workload shows parity, not a material benefit. Replacing the current scorer would add a mechanism without demonstrated retrieval lift.

The third-arm gate is **closed**:

```text
eligible_for_research: false
specific_shared_recall_failures: []
```

Therefore embeddings, rerankers, RRF, and other third mechanisms remain out of scope.

## Validated invariants

- `LEXICAL_V1` ordering matches production document ordering for the same query/branch fixture.
- both arms use the same resolved branch/dependency surfaces.
- requested-branch tier `0` remains ahead of dependency tier `1`.
- sibling documents are excluded from both candidate sets.
- injecting 50 sibling decoy documents does not alter scope-local FTS5 result order or scores.
- operator-looking query words and hyphenated identifiers are compiled as FTS literals.
- benchmark receipts are deterministic for the same projection/spec/revision.
- benchmark specs cannot inject a third arm.
- receipts require an exact 40-character Git revision identity.
- benchmark output remains `BENCHMARK_ONLY` with `authority_effect: NONE`.

## Remaining gap

This fixture is intentionally small and synthetic. It proves comparator correctness, scope isolation, and benchmark identity, but not a production retrieval advantage.

The next retrieval slice should expand **hard-negative and real repository query coverage** before changing production retrieval. A new mechanism should be considered only after a reproduced query class demonstrates a material failure in both fixed arms or a material benefit under held-out evaluation.
