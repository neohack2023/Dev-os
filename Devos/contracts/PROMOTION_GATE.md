# Promotion Gate Contract

The promotion gate converts a transfer-tested learning capability into a locked STONE promotion envelope and classifies external verification for MASON. It never performs the durable repository write itself.

## Entry conditions

A promotion envelope may be created only when:

- the capability exists in the local learning store,
- its latest maturity is `TRANSFER` or a future explicitly stronger stage,
- the bound evaluation passed held-out transfer,
- the bound evaluation is regression-safe,
- the evaluation resolves to a stored procedure,
- the procedure resolves to stored reflection candidates,
- those reflections preserve addressable evidence lineage,
- the target repository matches the current repository projection,
- the candidate revision is an exact 40-character Git SHA,
- the proposed change has a SHA-256 digest, bounded target paths, rollback plan, falsification test, required authorization, and explicit verifier policy.

A successful proposal is `STONE: LOCKED`, but remains `CANDIDATE_ONLY` with `authority_effect: NONE` and `write_authorized: false`.

## Verification contract

All required checks are matched by both check name and verifier source. Every supplied status check, review, and canary must bind to the exact candidate revision in the envelope. Revision mismatch is an integrity error, not a soft failure.

When configured, independent review must come from the named review source, be approved, and not be self-review. Required canaries must come from the named canary source and succeed for the exact candidate revision. Rollback readiness is required for `PROMOTE`.

The gate derives one of four outcomes:

- `PROMOTE`: all configured gates passed; eligible for MASON review/handoff.
- `REVISE`: one or more required gates are missing, failing, or rollback was triggered but not verified.
- `ROLLBACK`: rollback was triggered and independently verified; eligible for MASON rollback review/handoff.
- `NO_OP`: an explicit no-op reason closes the candidate without mutation.

`PROMOTE` and `ROLLBACK` are handoff classifications only. Every decision keeps `write_authorized: false`.

## Executable candidate identity

A promotion envelope always carries an exact candidate Git revision and SHA-256 `change_digest`. When the candidate is intended for `MASON_EXECUTION_PORT_01`, the digest must use the `sha256-git-diff-v1` algorithm defined by `contracts/MASON_EXECUTION.md`: the SHA-256 of the canonical raw Git diff between the exact authorized base revision and candidate revision.

The promotion gate does not infer the base revision and does not itself execute this Git verification. MASON preparation supplies the base revision, recomputes the canonical diff and exact changed-path set, and fails closed if either differs from the locked STONE envelope.

## Persistence

Promotion envelopes and decisions are immutable/idempotent durable runtime state. Exact replay does not create duplicate receipts. Ordinary knowledge-projection rebuilds preserve them.

The gate must not foreign-key durable promotion state to rebuildable projection tables. Branch/repository identity is validated at admission.

## External controls

Repository protection remains external authority. Required status checks, pull-request review, environment/deployment protection, merge queues, or equivalent host controls should enforce the actual remote write path. Verifier evidence should identify the exact revision and trusted source.

A local MASON execution receipt does not prove or authorize a GitHub mutation. Remote GitHub authority requires a separate adapter/receipt that respects the host repository's protection and authorization controls.
