# KNOWLEDGE STATE TRAJECTORY

Status: candidate contract
Slice: `KNOWLEDGE_STATE_TRAJECTORY_01`

## Purpose

Preserve not only the durable assertions that existed before and after a knowledge change, but also the evidence-backed reason the change occurred.

A knowledge subject is not modeled as one mutable value. It is modeled as:

```text
stable subject
  -> immutable assertion A
  -> transition artifact with reason + basis
  -> immutable assertion B
  -> transition artifact with reason + basis
  -> immutable assertion C
```

The transition is a first-class artifact. It is not inferred from timestamps and it is not replaced by the fact that two assertions have a lineage edge.

## Core law

`CURRENT STATE WITHOUT CHANGE BASIS IS INCOMPLETE MEMORY.`

A lineage relation answers **what changed**. A state-transition artifact answers **why that relation is justified**.

For every admitted `CONFIRMS`, `SUPERSEDES`, or `CONFLICTS` transition that is material to retrieval or governance, preserve:

- stable subject identity;
- source assertion identity;
- target assertion identity;
- relation type;
- explicit human- or evidence-readable reason;
- one or more basis/evidence references;
- effective time;
- recorded time;
- optional trigger and governed decision references.

## Separation of evidence

Assertion evidence and transition evidence are related but distinct.

- assertion evidence supports the claim represented by an assertion;
- transition evidence supports why one assertion confirms, supersedes, or conflicts with another.

Do not assume the evidence attached to the newer assertion automatically explains why the previous assertion ceased to be current.

## Retrieval behavior

When a current assertion is returned and a previous durable assertion exists, the retrieval layer should be able to expose the bounded trajectory on demand:

```text
current assertion
  <- SUPERSEDES
prior assertion
  <- because: <reason>
  <- basis: <evidence refs>
```

Routine retrieval may return only the current assertion plus a compact transition summary. Provenance challenge, audit, conflict resolution, or explanation tasks may expand the full trajectory.

## Authority boundary

A transition artifact records a justified state relationship. It does not create source authority.

- GitHub remains repository execution truth where declared.
- external memory remains authoritative only in its declared domain.
- `SUPERSEDES` never means "newer timestamp wins" by itself.
- a transition with weak or unavailable basis may remain candidate, contested, or unresolved.

## Destructive overwrite prohibition

Never replace assertion A with assertion B and discard the path between them.

History may be compacted for retrieval, but the immutable assertion identities, relation, and transition basis remain available as evidence.

## Cross-layer use

This contract composes with `CROSS_LAYER_KNOWLEDGE_EDGE`.

The edge identifies which external/local knowledge objects relate across Notion and DevOS. The trajectory identifies how a durable knowledge state changed through time. They solve different problems and must not be collapsed.

## Candidate implementation boundary

Slice 01 adds:

- `knowledge-state-transition.schema.json`;
- deterministic transition IDs;
- validation that reason and basis are present;
- optional assertion and lineage-edge consistency checks;
- deterministic trajectory ordering.

It does not yet:

- persist transitions into the runtime SQLite schema;
- change current-state derivation;
- automatically emit STONE/MASON records;
- authorize Notion or repository writes outside the normal governed path.
