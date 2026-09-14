# REDDIT_CANDIDATE_INGEST_01

Status: **accepted local checkpoint**

## Objective

Turn `STONE-20260914-DEVOS-REDDIT-HARVEST-03` into executable, provenance-bound DevOS runtime knowledge without shipping host-specific SQLite state or silently promoting research into authority.

## Deliverables

- `runtime/candidate_ingest.py`
- `knowledge/reddit-harvest-03.json`
- `tests/test_candidate_ingest.py`

## Ingestion contract

`candidate_ingest.py` materializes each entry through the existing governed chain:

```text
evidence root + atomic finding
→ evidence delta
→ immutable reflection candidate
→ candidate procedure/evaluation/experience/capability
```

The importer binds `branch_scope`, `source_reflection_ids`, and `source_evidence_refs` itself. A pack is rejected if it tries to supply those lineage-controlled procedure fields.

The pack uses `source-recognition-only/v1`: T0 contract and T1 source-recognition fixtures pass, while T2 development and T3 held-out fixtures are explicitly false. The resulting capabilities therefore stop at `RECOGNITION`; they are not transfer-qualified.

## Candidate memories admitted

1. `retrieval-workload-dependence` — **SEMANTIC**. Conflicting external retrieval results require DevOS-local ablation before architecture promotion.
2. `benchmark-claim-identity` — **PROCEDURAL**. Benchmark claims need reproducible evaluator/metric, input/dataset, revision, and relevant configuration identity before influencing decisions.
3. `resume-revalidation` — **PROCEDURAL**. A handoff is in-flight witness state; repository state must be revalidated before resumed execution.
4. `memory-infrastructure-justification` — **NEGATIVE**. Novel memory infrastructure requires a measured active failure or bounded improvement target.

All four remain `CANDIDATE_ONLY` with `authority_effect: NONE`.

## Runtime-state boundary

The distribution still does **not** ship `Devos/state/devos-knowledge.db`. An initialized host materializes the pack into its own runtime database with:

```text
python Devos/runtime/candidate_ingest.py Devos/knowledge/reddit-harvest-03.json
```

Normal knowledge-projection rebuilds preserve the durable evidence, reflection, and learning tables already owned by the runtime schema.

## Validation

Exact pre-checkpoint candidate:

`3e0e9d0db049b7504e99205be6bf67424feefb80`

PR: `#1` — `Ingest governed Reddit learning candidates`

GitHub Actions on that exact candidate:

- DevOS Portable Validation — run `34850913615` — **success**
- DevOS GitHub Authority Validation — run `34850913320` — **success**
- DevOS GitHub Policy Validation — run `34850913368` — **success**

Deterministic ingestion tests cover:

- four candidate memories materialized through evidence → reflection → learning
- 8 evidence roots, 8 atomic findings, 4 deltas, 4 reflections, 4 experiences, 4 procedures, and 4 capabilities
- exact replay idempotency
- no duplicate capability lifecycle events on replay
- rejection of pack-supplied lineage-controlled evidence fields
- rejection of unknown branch scope
- explicit `RECOGNITION` maturity ceiling with no transfer claim

## Remaining gaps

This checkpoint proves governed ingestion, not the behavioral utility of the four candidates. Separate slices are still required for `DEVOS_RETRIEVAL_ABLATION_01`, `DEVOS_BENCHMARK_CLAIM_RECEIPT_01`, and `DEVOS_RESUME_PACKET_PORT_01`, each with development, held-out transfer, regression, and canary evidence appropriate to its risk.
