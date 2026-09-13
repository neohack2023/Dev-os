# Evidence Runtime Contract

DevOS evidence is durable runtime state used to describe observations without silently upgrading authority.

## Admission boundary

An evidence episode must declare:

- `episode_id`
- `branch_key`
- `claim_key`
- explicit `observed_at`
- zero or more current claims used only for deterministic cross-reference
- evidence roots with provenance
- one or more atomic findings

The referenced branch must exist at admission time. Root and finding identifiers are immutable identities: replaying identical content is idempotent; reusing an identifier with different content is a hard error.

## Lineage law

Independent-root counts may come only from `INDEPENDENT_ROOT` and `REPLICATION_NEW_INPUTS` findings. Derived, revised, quoted, shared-root, and same-input reproduction artifacts do not create independent votes. Partial shared-input evidence remains correlated. Unknown lineage blocks strong convergence when independent evidence is insufficient.

## Cross-reference and triangulation

Cross-reference is keyed by explicit `claim_key`; the runtime does not infer semantic claim identity. Outcomes are `NEW`, `SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `PARTIAL_OVERLAP`, or `INSUFFICIENT`.

Triangulation yields `CONVERGENCE`, `DIVERGENCE`, `SINGLETON`, `ORTHOGONAL`, or `INSUFFICIENT` after lineage collapse.

## Authority boundary

Every evidence delta packet has `authority_effect: NONE`. A delta may recommend review, but it may not mutate repository authority, governance, tasks, learning state, or project canon. Durable promotion still routes through STONE -> MASON and the authorized repository write path.

## Persistence boundary

Evidence tables are durable runtime state. Normal knowledge projection rebuilds must preserve them. `build_knowledge_db.py build --fresh` remains the explicit destructive database reset.

Evidence must not foreign-key durable rows to rebuildable projection rows. Projection identity such as branch existence is checked at admission time and then recorded as provenance context.
