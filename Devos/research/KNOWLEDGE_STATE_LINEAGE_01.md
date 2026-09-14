# KNOWLEDGE_STATE_LINEAGE_01 Research and Evaluation

Date: 2026-09-14
Base revision: `78c87df389c0718828c76f648ac1729d928c361b`

## Problem

DevOS already preserves evidence, reflection, learning, promotion, and repository authority, but its durable knowledge projection does not yet provide a stable identity for a knowledge subject across changing claims. Without explicit lineage, later information can either overwrite useful history or leave conflicting material indistinguishable from corroboration.

## External evidence

### W3C PROV

W3C PROV-DM treats provenance as information about entities, activities, and responsibility, and defines derivation, revision, invalidation, and relations between entities that refer to the same thing. A revision is modeled as a new entity derived from a preceding entity rather than destructive mutation of the preceding entity.

Source: https://www.w3.org/TR/prov-dm/

Useful transfer: keep immutable assertion instances and explicit relations between them. DevOS-specific `CONFIRMS`, `SUPERSEDES`, and `CONFLICTS` are narrower domain relations, not claims of full PROV compliance.

### Bitemporal history

Martin Fowler's bitemporal history distinguishes the time a fact applies from the time the system learned it. Record history remains append-only even when knowledge about actual history changes retroactively.

Source: https://www.martinfowler.com/articles/bitemporal-history.html

Useful transfer: preserve `effective_at` separately from `recorded_at`. Do not implement the full bitemporal machinery until a real query need appears.

### Stable domain identity

Datomic distinguishes immutable database entity ids from unique domain identities and uses unique identity attributes to resolve repeated observations to the same logical entity.

Source: https://docs.datomic.com/schema/identity.html

Useful transfer: derive a stable subject identity from `(scope_key, knowledge_key)`, while assertion identities remain separate and immutable.

### Event sourcing

Microsoft's event-sourcing guidance emphasizes append-only change history, auditability, and projections, while explicitly warning that full event sourcing changes concurrency, schema evolution, and query design and should be adopted only when its benefits justify that complexity.

Source: https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing

Useful transfer: use append-only assertion/edge records and derive current state, but do not convert the rest of DevOS into an event store.

## Repository cross-reference

The live DevOS agent contract already requires STONE to preserve provenance, rejects, uncertainty, and conflicts, and forbids external memory from overriding repository execution facts. The current SQLite runtime is schema v8 and already uses additive, signed migrations. The knowledge runtime builds a deterministic repository-local projection but does not model claim lineage.

Relevant current files:

- `Devos/AGENTS.md`
- `Devos/runtime/db_runtime.py`
- `Devos/runtime/build_knowledge_db.py`
- `Devos/runtime/knowledge_runtime.py`
- `Devos/contracts/KNOWLEDGE_RUNTIME.md`

## Options evaluated

### A. Overwrite current knowledge rows

Rejected. Simple, but loses audit history and makes stale truth indistinguishable from a corrected record.

### B. Full event sourcing / bitemporal database

Rejected for this slice. Strong historical semantics, but unnecessarily expands the storage and query model across unrelated DevOS subsystems.

### C. Stable subjects + immutable assertions + explicit lineage edges

Accepted. It fits the existing additive SQLite migration model, preserves provenance, supports deterministic validation, exposes conflicts instead of hiding them, and leaves room for later temporal/retrieval integration.

## Selected invariants

1. Stable identity is `(scope_key, knowledge_key)` and deterministically maps to one `subject_id`.
2. A subject's knowledge kind cannot silently change.
3. Assertions are immutable and retain canonical claim hashes, evidence refs, `effective_at`, and `recorded_at`.
4. Lineage never crosses subjects.
5. `CONFIRMS` requires identical canonical claim content.
6. `SUPERSEDES` and `CONFLICTS` require different canonical claim content.
7. `SUPERSEDES` is acyclic and points `newer -> older`.
8. Current state is a projection: superseded assertions are excluded; multiple remaining claim hashes yield `CONTESTED`.
9. Relation count is not authority. Repository governance remains authoritative for executable state.
10. No semantic model guesses equivalence in this deterministic slice.

## Expected value

This prevents the failure class where obsolete information is retrieved as if it were current, while retaining the evidence trail needed to explain how DevOS changed its mind. It also gives future retrieval work a deterministic gate: prefer `ACTIVE`; surface or block on `CONTESTED`; retain superseded history for audit.

## Follow-on, not included

- integrate current-state filtering into `knowledge_runtime.py` retrieval;
- STONE/MASON helpers that emit lineage automatically when durable facts are admitted;
- explicit conflict-resolution receipts;
- bitemporal queries over effective and record time;
- cross-source semantic normalization before relation creation.
