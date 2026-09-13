# EVIDENCE_RUNTIME_PORT_01

Status: portable executable checkpoint.

## Source lineage

Neutralized from Project Orath:

- `tools/evidence_runtime.py` blob `0af8ef46001d66ceeb44497e2c127c39c2264d01`
- `tools/evidence_store.py` blob `09873d6e3085b3709245009df3b9bf932f20a7c0`
- source tests `tests/test_evidence_runtime.py` blob `fc7ab49dbf00e3867467f72eb34279b805fe7a74`

## Portable result

- `runtime/evidence_runtime.py` implements explicit claim cross-reference, lineage collapse, independent-root triangulation, and authority-neutral delta packets.
- `runtime/evidence_store.py` admits evidence episodes into SQLite with immutable/idempotent identity semantics.
- `schemas/runtime-db-v2.sql` adds durable evidence roots, findings, root edges, assessments, triangulation batches, and delta packets.
- `schemas/evidence-episode.schema.json` defines the portable input shape.
- evidence timestamps come from explicit `observed_at`, not implicit wall-clock time.

## Invariants proven

- derivative artifacts do not inflate independent support;
- same-input reproduction is not a new root;
- independent replication can converge;
- independent disagreement produces divergence;
- supersession remains review-only;
- all delta packets have `authority_effect: NONE`;
- identical episode replay is idempotent;
- identifier reuse with changed content is rejected;
- unknown branches and roots are rejected;
- normal knowledge projection rebuilds preserve durable evidence.

## Discovered anti-pattern

The first implementation foreign-keyed durable `atomic_findings.branch_key` to rebuildable `branch_state`. CI correctly showed that projection refresh would then fail after evidence admission. The final design checks branch validity at admission time but stores the branch key without a database FK across the durable/projection boundary.

## Deferred

Reflection, learning thresholds, curriculum selection, and authority promotion remain separate later slices. Evidence does not self-promote.
