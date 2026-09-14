# GitHub Authority Adapter Contract

The GitHub authority adapter is the only portable DevOS layer in this slice allowed to turn a successful local MASON result into verified GitHub branch authority.

## Entry conditions

The adapter starts from an immutable MASON receipt whose outcome is `APPLIED`, whose `post_revision` equals the exact candidate revision, and whose remote authority/write fields still report `NONE` / `false`.

A remote request must carry explicit `GITHUB_PR_MERGE` authorization bound to the MASON receipt, repository, target branch, candidate branch, and exact candidate SHA.

The remote candidate branch must already exist on GitHub and point to the exact candidate SHA. The target branch must still equal the MASON base SHA when the authority plan is prepared.

## Policy gate

The adapter reads active GitHub branch/ruleset policy and hashes the resulting policy snapshot into the immutable authority plan.

It fails closed when:

- no branch protection or active rules apply,
- active protection exists but cannot be inspected well enough to prove the configured gate,
- pull-request governance is not required,
- no required status check exists,
- the policy changes after plan preparation,
- the target branch or candidate branch drifts.

This first slice preserves exact candidate identity and therefore supports the normal merge-commit path only. Policies requiring merge queue, linear history/rebase, or required deployments are reported as unsupported rather than silently rewriting candidate identity.

## PR and latest-SHA verification

The pull request head must equal the authorized candidate SHA and the base must equal the authorized target branch. Required checks are evaluated on that candidate SHA. Required approving-review count is checked before merge. GitHub must also report the PR mergeable.

The adapter passes the candidate SHA to GitHub's merge endpoint as an expected head identity. GitHub remains responsible for enforcing repository protections at the actual merge boundary.

## Authority receipt

A successful merge is not accepted until the adapter independently verifies that:

- GitHub returned a merge commit SHA,
- the target branch now points to that SHA,
- the merge commit contains the exact candidate SHA as a parent.

Only then may an immutable receipt claim:

- `outcome: MERGED`
- `remote_authority_effect: GITHUB_TARGET_BRANCH_UPDATED`
- `remote_write_performed: true`

The authority receipt preserves the MASON receipt ID, PR number, base SHA, candidate SHA, authoritative merge SHA, change digest, and policy digest.

## Non-goals

This slice does not bypass branch protection, create protection/rulesets, push missing candidate commits, use merge queues, squash/rebase candidates, or claim authority from an unprotected direct ref update.
