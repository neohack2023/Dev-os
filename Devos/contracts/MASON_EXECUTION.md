# MASON Execution Contract

MASON execution consumes a verified `PROMOTE` decision and a locked STONE promotion envelope. It may materialize that already-reviewed candidate in a local Git checkout, but it does not generate source changes, push to a remote, bypass repository protection, or grant itself authority.

## Scope

This slice supports one execution mode: `LOCAL_GIT_FAST_FORWARD`.

The executor advances the currently checked-out target branch from an explicitly authorized base revision to the exact candidate revision using `git merge --ff-only`. The candidate must already exist as a local Git commit.

Remote GitHub authority remains unchanged. Every plan and receipt records `remote_write_authorized: false` or `remote_write_performed: false`. A successful local receipt uses `local_authority_effect: LOCAL_GIT_REF_UPDATED` and `remote_authority_effect: NONE`.

## Entry conditions

Execution preparation requires:

- an immutable promotion decision whose outcome is `PROMOTE`,
- `next_action: MASON_REVIEW_PROMOTION`,
- the corresponding locked STONE envelope,
- a promotion gate that did not pre-authorize writes,
- explicit MASON authorization with grant `MASON_FAST_FORWARD`,
- authorization identity bound to the decision ID, envelope ID, candidate revision, target branch, and the envelope's required-authorization scope,
- an exact 40-character base Git SHA,
- a clean local Git worktree on the target branch,
- the current `HEAD` equal to the authorized base revision,
- the candidate revision present as a local commit and reachable by fast-forward from the base,
- an exact changed-path set equal to the locked STONE target paths,
- an exact canonical Git diff digest equal to the locked STONE `change_digest`.

Any mismatch fails closed before mutation.

## Canonical candidate digest

Executable promotion candidates use `sha256-git-diff-v1`:

1. Run Git diff from the exact base revision to the exact candidate revision.
2. Use binary/full-index output with color, external diff, text conversion, and rename detection disabled.
3. Hash the raw diff bytes with SHA-256.

The executor also independently derives the changed-path set from the same base/candidate pair. The locked target paths must equal that set exactly.

## Git safety boundary

MASON does not execute repository hooks. Git commands run with `core.hooksPath=/dev/null` and filesystem monitoring disabled. Global and system Git configuration are ignored for MASON operations.

Repositories with local `filter.*.smudge` or `filter.*.process` commands are refused. This prevents an apparently simple checkout/fast-forward from becoming an implicit arbitrary-command channel.

MASON refuses detached HEAD state and dirty worktrees. It does not run arbitrary shell commands supplied by a candidate, does not apply caller-provided patches, and does not invoke force/reset-based promotion.

## Mutation

After a plan is persisted, `apply` repeats the full preflight to detect drift. Only then may it run:

```text
git merge --ff-only --no-edit <candidate-revision>
```

No other source mutation primitive is part of this slice.

## Post-write verification

After the fast-forward, MASON independently verifies:

- `HEAD` exactly equals the candidate revision,
- the checked-out branch is still the target branch,
- the worktree is clean,
- the changed-path set still equals the locked target paths,
- `sha256-git-diff-v1` still equals the locked change digest,
- the resulting Git tree object is addressable and recorded.

Only then may the receipt outcome be `APPLIED`.

## Receipts and failure semantics

Execution plans and receipts are durable SQLite runtime state and survive normal knowledge-projection rebuilds.

Each plan may produce exactly one immutable receipt. Exact replay of an `APPLIED` plan returns the same receipt and does not execute Git again.

If preflight or post-write verification fails after `apply` begins, MASON records one immutable `FAILED` receipt after writes stop and reports failure. A failed plan is not silently retried; a new governed plan is required.

The receipt records the base revision as `rollback_revision`, but this slice does not automatically rewrite history or force a branch backward. Rollback remains a separately authorized MASON action.

## Remote authority boundary

A local fast-forward receipt is not proof that GitHub changed. Remote repository authority still depends on the host's protected-branch, pull-request, status-check, deployment, merge-queue, and authorization rules.

A future remote adapter may consume an `APPLIED` local receipt, re-verify the exact candidate and protection state, perform the permitted remote action, and emit a separate remote-authority receipt. This contract must not be interpreted as permission to bypass that step.
