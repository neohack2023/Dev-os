# Learning Layer Contract

Status: portable executable contract

The learning layer turns evidence-bounded reflection into reusable candidate experience without granting repository authority.

## Lineage

The required lineage is:

`admitted evidence -> evidence delta -> stored reflection candidate -> learning candidate`

A learned procedure MUST name one or more stored reflection candidates. Its evidence references MUST be a subset of evidence already preserved by those reflections. Learning may compress or generalize; it may not manufacture support.

## Memory forms

Portable learning recognizes four candidate memory forms:

- `EPISODIC`: what happened in a bounded episode.
- `SEMANTIC`: a generalized candidate statement derived from episodes.
- `PROCEDURAL`: a reusable procedure contract. Requires a procedure identity.
- `NEGATIVE`: a known failure, anti-pattern, unsafe assumption, or invalid procedure.

All remain `CANDIDATE_ONLY` with `authority_effect: NONE`.

## Evaluation tiers

- `T0`: invariant/contract checks.
- `T1`: known/training examples.
- `T2`: development variations.
- `T3`: held-out transfer inputs. T3 input identities MUST be disjoint from T1/T2.
- `T4`: adversarial/regression checks.
- `T5`: real-work canary.

`TRANSFER` requires T0-T3 to pass. T4 and T5 are recorded separately as `regression_safe` and `canary_validated`.

This slice MUST NOT infer `COMPOSITION`, `ADAPTATION`, or `METACOGNITIVE_CONTROL` from T4/T5. Those maturity stages require future dedicated contracts.

## Persistence

Procedures, evaluations, experiences, capabilities, and capability lifecycle events are durable runtime state. Normal knowledge projection rebuilds MUST preserve them.

Identical procedure/evaluation/experience replay is idempotent. Capability lifecycle history grows only when the learned state changes; exact replay MUST NOT fabricate another event.

Durable learning tables may foreign-key other durable learning/reflection tables. They MUST NOT foreign-key rebuildable projection tables such as `branch_state`.

## Authority boundary

Learning can nominate reusable knowledge, procedures, and capabilities. It cannot:

- mutate repository canon,
- rewrite governance,
- promote itself,
- mark a reflection true,
- bypass STONE or MASON,
- substitute memory prevalence for transfer evidence.

Promotion remains a separate governed act after evaluation, review, and required repository gates.
