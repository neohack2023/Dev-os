# Knowledge State Lineage

`KNOWLEDGE_STATE_LINEAGE_01` gives DevOS durable knowledge a stable identity without turning mutable truth into destructive overwrite.

## Identity model

A knowledge subject is identified by the pair `(scope_key, knowledge_key)`. Its deterministic `subject_id` remains stable while assertions about that subject change.

Assertions are immutable observations of a canonical claim plus evidence references and time metadata. New information creates a new assertion. Existing assertion rows are never edited to manufacture a cleaner history.

## Lineage relations

All relations are scoped to one stable knowledge subject.

- `CONFIRMS`: the new assertion has the same canonical claim content as the assertion it confirms. Independent evidence may differ.
- `SUPERSEDES`: the newer assertion replaces an older, different claim for current-state purposes. The older assertion remains queryable as history.
- `CONFLICTS`: two different current claims are both retained. Conflict does not grant either claim authority or silently choose a winner.

`SUPERSEDES` edges form an acyclic graph. Edge direction is `newer -> older`.

## Current-state projection

Current state is derived, not stored as a mutable truth field.

An assertion is current when it is not the target of a `SUPERSEDES` edge. Current assertions are grouped by canonical claim hash:

- no current assertion: `EMPTY`
- one canonical current claim: `ACTIVE`
- more than one canonical current claim: `CONTESTED`

Multiple current assertions with the same claim increase support count; they do not create competing state.

## Authority rules

Lineage records provenance and state evolution. It does not decide authority by itself.

Repository execution truth remains authoritative for executable code. External research or memory may confirm, supersede, or conflict with an assertion, but a lineage edge cannot elevate a source above repository governance.

A `CONTESTED` state must remain visible to downstream retrieval or evaluation until a governed evidence process resolves it. No relation may cross stable knowledge identities or project scopes.

## Time model

The first slice records both `effective_at` (when the claim applies, if known) and `recorded_at` (when DevOS learned it). This preserves the minimum shape needed for later bitemporal reasoning without implementing a full bitemporal query engine in this slice.

## Non-goals

This slice does not:

- convert all DevOS storage to event sourcing;
- automatically infer semantic equivalence between differently worded claims;
- assign trust scores from relation count;
- automatically resolve conflicts;
- replace STONE evidence admission, reflection, learning, or promotion gates;
- rewrite the existing document retrieval projection.
