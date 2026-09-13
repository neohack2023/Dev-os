# PROMOTION_GATE_PORT_01

Status: candidate until exact-head CI passes and the same head is promoted to `main`.

## Goal

Close the executable self-improvement loop without granting learning or reflection direct repository-write authority.

Chain:

`evidence -> reflection -> learning -> STONE promotion envelope -> verifier decision -> MASON handoff`

## Design basis

Existing portable contracts:

- `contracts/STONE.md`
- `contracts/MASON.md`
- `contracts/SELF_IMPROVEMENT.md`
- `contracts/LEARNING_LAYER.md`

External guidance reviewed for this slice:

- GitHub required status checks and rulesets: checks must protect the actual candidate revision; repository rules may require PRs, status checks, deployments, and restrict bypass.
- GitHub deployment environments: protected environments can require reviewers and other deployment protection rules.
- SLSA provenance/verification: provenance is useful only when the consumer verifies artifact/source identity against expectations; immutable attestations and exact digests are preferred.
- NIST SSDF / DevSecOps guidance: release readiness should gather evidence of required tests and maintain an explicit rollback path; current SSDF work also emphasizes staged updates and robust rollback mechanisms.

## Portable implementation

- `runtime/promotion_gate.py`
- `schemas/runtime-db-v5.sql`
- `schemas/promotion-request.schema.json`
- `schemas/promotion-verification.schema.json`
- `tests/test_promotion_gate.py`
- `contracts/PROMOTION_GATE.md`

SQLite schema version: 5.

## Core invariants

1. A capability below held-out `TRANSFER` cannot enter the promotion gate.
2. The bound evaluation must be `validated_for_transfer` and `regression_safe`.
3. Learning provenance must resolve through procedure -> reflection -> evidence lineage.
4. Target repository identity must match the current host projection.
5. Candidate revision is an exact 40-character lowercase Git SHA.
6. Change identity includes a SHA-256 digest and explicit target paths/ref.
7. Required verifier checks match both name and source.
8. Every check/review/canary must bind to the exact candidate revision.
9. Independent review cannot be satisfied by self-review.
10. `PROMOTE` requires all configured gates plus rollback readiness.
11. `ROLLBACK` requires an explicit triggered and verified rollback signal.
12. `PROMOTE` and `ROLLBACK` are MASON handoff classifications, never direct write authorization.
13. Every envelope/decision has `authority_effect: NONE`, `promotion_state: CANDIDATE_ONLY`, and `write_authorized: false`.
14. Exact replay is idempotent; changed verification creates a new immutable decision.
15. Normal projection rebuilds preserve promotion envelopes and decisions.

## Anti-patterns captured

- Do not accept a caller-supplied final promotion verdict. Derive it from configured gates.
- Do not let a successful historical check satisfy a different candidate SHA.
- Do not treat provenance as trust by itself; bind verifier source and verify expectations.
- Do not let the learning layer mutate repository authority directly.
- Do not use `PROMOTE` as a synonym for `push`, `merge`, or `deploy`.
- Do not create durable-state foreign keys into rebuildable repository projection tables.

## Acceptance gates

- unit tests cover regression-safe admission, exact revision binding, missing gates -> `REVISE`, full gates -> `PROMOTE`, verified rollback, idempotence, and rebuild persistence;
- package validation includes all promotion files;
- public CI exercises the complete evidence -> reflection -> learning -> promotion chain;
- exact staging head passes Actions;
- `main` is fast-forwarded only after exact-head success and must pass the same workflow again.
