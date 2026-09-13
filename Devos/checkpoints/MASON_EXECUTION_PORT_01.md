# MASON_EXECUTION_PORT_01

Status: CANDIDATE until the exact sealing head is green in CI and promoted to `main`.

## Objective

Close the first executable STONE -> MASON write boundary without turning DevOS into an unbounded repository writer.

The slice consumes a verified `PROMOTE` handoff and can advance only a local Git branch by fast-forward to the exact reviewed candidate commit. It emits immutable execution receipts and explicitly leaves remote GitHub authority unchanged.

## Research basis

Current GitHub guidance requires protected-branch checks to pass on the latest commit SHA and allows required checks to be bound to a specific GitHub App/source. Protected branches and rulesets can require reviews, deployments, merge queues, and status checks before remote mutation. SLSA provenance guidance similarly treats provenance as useful when a consumer verifies production details against explicit expectations.

Those findings reinforced four design decisions:

1. Candidate identity stays revision-bound end to end.
2. MASON re-verifies instead of trusting promotion metadata blindly.
3. Local execution and remote authority are separate receipts/effects.
4. The executor never bypasses host branch-protection machinery.

## Implemented

- `runtime/mason_execution.py`
- `schemas/runtime-db-v6.sql`
- `tests/test_mason_execution.py`
- `contracts/MASON_EXECUTION.md`
- SQLite schema version 6

## Execution model

`LOCAL_GIT_FAST_FORWARD` only.

Preparation binds:

- promotion decision,
- STONE envelope,
- exact base revision,
- exact candidate revision,
- exact target branch,
- exact target paths,
- canonical Git diff digest,
- explicit authorization identity and scope.

Apply repeats preflight, executes only `git merge --ff-only --no-edit <candidate>`, and then independently verifies the resulting branch, HEAD, tree cleanliness, changed paths, diff digest, and tree SHA.

## Canonical diff identity

`sha256-git-diff-v1` hashes raw bytes from a binary/full-index Git diff between the exact base and candidate revisions with color, external diff, text conversion, and rename detection disabled.

## Safety hardening

- clean worktree required,
- detached HEAD refused,
- candidate must be a fast-forward descendant,
- changed paths must exactly equal the locked STONE target,
- Git hooks disabled for MASON commands,
- global/system Git config ignored for MASON commands,
- local smudge/process filter commands refused,
- no arbitrary shell command execution,
- no patch application primitive,
- no reset/force promotion primitive,
- no remote push in this slice.

## Receipt model

A plan may produce one immutable receipt.

`APPLIED` records:

- pre/base revision,
- candidate/post revision,
- target branch,
- resulting tree SHA,
- exact changed paths,
- exact change digest,
- clean-worktree verification,
- `local_authority_effect: LOCAL_GIT_REF_UPDATED`,
- `remote_authority_effect: NONE`,
- `remote_write_performed: false`,
- rollback revision.

Failure after `apply` begins writes one immutable `FAILED` receipt after writes stop. Failed plans are not silently retried.

## Acceptance gates

1. Non-`PROMOTE` decisions fail closed.
2. Authorization must match the locked handoff identity and scope.
3. Dirty worktrees fail closed.
4. Detached/wrong branch or base revision drift fails closed.
5. Candidate must be a fast-forward descendant.
6. Changed-path escape fails closed.
7. Diff digest mismatch fails closed.
8. Active local smudge/process filter commands fail closed.
9. Successful apply fast-forwards to the exact candidate and verifies post-state.
10. Exact successful replay is idempotent and does not execute Git twice.
11. Failed apply produces one immutable failure receipt.
12. Normal knowledge-projection rebuild preserves plans and receipts.
13. Package validation requires the runtime/schema/test/contract/checkpoint.
14. Public CLI execution gate passes in CI on the exact sealing head.
15. Main-branch CI passes again on the exact promoted tree.

## Explicit non-goals

- pushing or merging on GitHub,
- bypassing protected branches or rulesets,
- force-updating a branch,
- automatic rollback/history rewrite,
- generating source code during execution,
- running candidate-provided commands.

The next remote-authority slice should be a GitHub adapter that consumes the immutable local MASON receipt and respects repository protection instead of duplicating it.
