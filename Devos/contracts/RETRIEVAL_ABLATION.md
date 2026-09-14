# DEVOS_RETRIEVAL_ABLATION_01

Status: **benchmark-only / read-only / promotion-locked**

## Objective

Compare the current DevOS branch-aware lexical document scorer against one SQLite FTS5 BM25 arm without changing production retrieval behavior.

This slice answers one bounded question:

> On the same branch-resolved document corpus, do `LEXICAL_V1` or `FTS5_BM25_V1` retrieve the frozen relevant evidence more reliably under DevOS scope and packet constraints?

## Fixed arms

### `LEXICAL_V1`

Authority source: `runtime/knowledge_runtime.py`.

The comparator imports the current `_tokens`, `_score`, branch resolution, and branch-tier behavior directly. It preserves the production document weights:

- title: `6`
- section: `4`
- path: `3`
- content: `1`
- exact raw-query substring bonus: `weight * 4`

This arm is a baseline. The ablation slice must not rewrite `_score()`.

### `FTS5_BM25_V1`

SQLite FTS5 BM25 over the same branch-eligible corpus.

Column weights follow the same relative field priorities:

- path: `3.0`
- title: `6.0`
- section: `4.0`
- content: `1.0`

The arm uses `fts5-literal-or-v1`: DevOS tokenizes the query with the current runtime tokenizer, drops punctuation-only tokens, quotes every remaining token as a literal FTS5 phrase, and joins literals with `OR`. User text is never passed directly into `MATCH`.

FTS5 is materialized into an ephemeral in-memory index containing only documents admitted by the resolved branch/dependency surfaces. This keeps both candidate formation and BM25 corpus statistics inside the lawful scope instead of allowing sibling documents to affect ranking statistics.

Direct requested-branch documents remain tier `0`; dependency documents remain tier `1`. Branch tier sorts before scorer rank in both arms.

## No third arm

This benchmark admits exactly two arms.

Do not add embeddings, vector search, rerankers, reciprocal-rank fusion, query expansion, or another retrieval mechanism in this slice.

A third-arm research candidate becomes eligible only if **both** fixed arms miss relevant evidence within top-5 on the same frozen query. The receipt must name those query IDs. Eligibility is permission to research a specific gap, not permission to add or promote a third mechanism.

## Frozen workload

`tests/fixtures/retrieval_ablation/benchmark.json` is the benchmark identity.

It covers:

- exact repository identifier retrieval
- natural-language multi-token retrieval
- title-weight competition
- dependency-surface retrieval
- hyphen/underscore identifiers
- path-term retrieval
- sibling-scope decoys
- direct-branch versus dependency ranking
- FTS operator-looking words treated literally
- a zero-result query

Queries are explicitly labeled `development` or `holdout`.

## Metrics

Per arm and split:

- Recall@1
- Recall@3
- Recall@5
- MRR
- expected-empty accuracy
- scope leakage count
- branch-tier violation count
- query IDs missed at top-5

These are retrieval metrics only. They do not establish downstream task utility.

## Receipt identity

Every run binds:

- exact candidate Git SHA
- projection digest
- benchmark-spec SHA-256
- SQLite version and source ID
- FTS5 availability
- arm identities and weights
- query compiler identity
- retrieval limit
- per-query results and aggregate metrics
- third-arm admission result
- receipt SHA-256

The result remains:

- `promotion_state: BENCHMARK_ONLY`
- `authority_effect: NONE`

## Runtime boundary

`runtime/retrieval_ablation.py` is read-only with respect to repository authority and DevOS durable learning state. It may build or refresh the normal host-local projection database and may write an explicitly requested benchmark receipt file. It does not change `knowledge_runtime.build_packet()`, learning maturity, STONE/MASON state, Git refs, or remote authority.

## Promotion rule

Do not replace production retrieval because one arm wins this fixture.

A production retrieval change requires a separate candidate slice with:

1. a demonstrated material retrieval gap or benefit,
2. held-out evidence,
3. regression and scope-isolation checks,
4. context-cost and latency accounting where relevant,
5. exact candidate validation,
6. the normal STONE → MASON → GitHub promotion path.
