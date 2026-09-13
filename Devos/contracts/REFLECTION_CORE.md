# Reflection Core Contract

## Purpose

`REFLECTION_CORE_PORT_01` converts admitted evidence deltas into bounded, falsifiable reflection candidates.

Reflection is diagnostic. It is not evidence, memory authority, canon, or promotion.

## Input boundary

The portable delta adapter accepts only an already-admitted `evidence_delta_packets` row plus a reflection request conforming to `schemas/reflection-request.schema.json`.

A request must declare:

- `branch_key`
- `expected_behavior`
- `mechanism_hypothesis`
- `evidence_for`
- `evidence_against`
- `alternative_explanations`
- `predicted_consequence`
- `required_disconfirmation_test`
- `proposed_scope`

## Hard invariants

1. `authority_effect` is always `NONE`.
2. `promotion_state` is always `CANDIDATE_ONLY`.
3. At least one supporting evidence reference is required.
4. Every `evidence_for` and `evidence_against` reference must already exist on the source delta.
5. At least one competing explanation is required and it must differ from the primary mechanism hypothesis.
6. A predicted consequence and explicit disconfirmation test are required.
7. Reflection identity is deterministic over the source delta, request semantics, and adapter identity context.
8. Identical replay is idempotent.
9. Competing hypotheses over the same delta remain separate candidates.
10. Reflection rows are durable runtime state and survive normal knowledge-projection rebuilds.
11. Branch validity is checked when a reflection is admitted; durable reflection rows do not foreign-key into rebuildable `branch_state`.
12. No numeric confidence score is treated as truth or authority.

## Anti-confabulation rule

Reflection may explain evidence, but it may not create evidence for itself. Self-generated prose cannot become a supporting reference merely because the model wrote it.

The disconfirmation test is part of the candidate contract so later evaluation can attack the hypothesis rather than merely repeat it.

## Durable state

SQLite schema v3 adds `reflection_candidates`.

A reflection row stores the complete candidate payload, deterministic source digest, row hash, source delta identity, branch/claim routing, and candidate-only authority state.

## Promotion boundary

Reflection can nominate a hypothesis or intervention target. It cannot:

- mutate repository authority,
- rewrite evidence,
- mark its hypothesis true,
- update canonical instructions,
- create an accepted learning,
- bypass STONE or MASON.

Any later promotion must be supported by new evidence and pass the applicable evaluation, transfer, regression, STONE, and MASON gates.
