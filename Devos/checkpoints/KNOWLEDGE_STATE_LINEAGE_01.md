# KNOWLEDGE_STATE_LINEAGE_01 Checkpoint

Date: 2026-09-14
Repository: `neohack2023/Dev-os`
Branch: `devos/knowledge-state-lineage-01`
Validated candidate: `58969b432d94496e537bab94c52a2fffff74ac6e`
DevOS version: `0.13.0`
Runtime schema: `v9`

## Validated slice

DevOS now models changing durable knowledge without destructive overwrite:

- stable subject identity from `(scope_key, knowledge_key)`;
- immutable assertion records with canonical claim hashes, evidence references, `effective_at`, and `recorded_at`;
- explicit `CONFIRMS`, `SUPERSEDES`, and `CONFLICTS` lineage edges;
- cross-subject lineage rejection;
- acyclic `SUPERSEDES` lineage with edge direction `newer -> older`;
- derived current state: `EMPTY`, `ACTIVE`, or `CONTESTED`;
- superseded assertions remain queryable as history;
- conflicting current assertions remain visible instead of being silently ranked or overwritten.

## Research basis

The design was selected after cross-referencing the live repository against:

- W3C PROV-DM revision/derivation and provenance concepts: https://www.w3.org/TR/prov-dm/
- Martin Fowler's bitemporal history distinction between effective history and record history: https://www.martinfowler.com/articles/bitemporal-history.html
- Datomic identity/uniqueness patterns for stable domain identity: https://docs.datomic.com/schema/identity.html
- Microsoft's event-sourcing guidance, especially append-only auditability and the complexity cost of full event sourcing: https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing

The accepted design is intentionally narrower than full event sourcing or a full bitemporal database.

## Validation evidence

Exact candidate `58969b432d94496e537bab94c52a2fffff74ac6e` passed:

- DevOS Portable Validation: run `34856823630`, job `104018421119`
- DevOS GitHub Authority Validation: run `34856823973`
- DevOS GitHub Policy Validation: run `34856823561`
- DevOS Retrieval Ablation: run `34856823844`

Portable validation passed package validation, the full DevOS unittest suite, task-queue fixture, repository fixture, knowledge DB build/query, branch-aware context packet, evidence admission, reflection, learning, promotion, and MASON local execution.

## Failure classification and learned negative knowledge

During the slice, early candidates failed because old package and test contracts pinned `0.12.0` / schema v8. The implementation itself had advanced additively to schema v9. These failures were classified as stale version-contract assumptions rather than lineage regressions.

The fix updated version/schema assertions while preserving all prior subsystem behavior and gates. No tests, policy checks, authority checks, or validation requirements were removed or weakened.

Negative lesson: additive runtime schema evolution must update every explicit global-version sentinel in tests and CI at the same slice boundary. Subsystem tests should continue checking their own tables/contracts, but a stale exact global schema number must not masquerade as a behavioral regression.

## Authority properties

Lineage records state evolution but does not decide repository authority. Relation count is not trust. External memory cannot use `CONFIRMS` or `SUPERSEDES` to outrank GitHub execution truth. A `CONTESTED` subject remains unresolved until governed evidence resolves it.

## Deferred work

Not included in this checkpoint:

- automatic STONE/MASON emission of lineage records;
- filtering `knowledge_runtime.py` retrieval through `ACTIVE` / `CONTESTED` state;
- conflict-resolution receipts;
- full bitemporal querying;
- semantic-equivalence inference between differently worded claims.

The next smallest useful slice is retrieval integration: expose current lineage state to context-packet selection so superseded assertions cannot re-enter executable reasoning as current truth and contested assertions are surfaced explicitly.
