# GITHUB_AUTHORITY_ADAPTER_PORT_01

## Goal

Close the remote-authority gap after `MASON_EXECUTION_PORT_01` without allowing local learning/promotion/execution layers to bypass GitHub governance.

## Result

Added a stdlib GitHub REST adapter that consumes an `APPLIED` MASON receipt, verifies an exact remote candidate branch, observes active branch/ruleset policy, binds that policy into an immutable plan, opens/reuses a PR, verifies latest-SHA checks and approvals, performs a merge-commit merge only when ready, and independently verifies the resulting target branch/merge parentage before emitting remote authority.

## New portable surfaces

- `runtime/github_authority_adapter.py`
- `schemas/runtime-db-v7.sql`
- `schemas/github-authority-request.schema.json`
- `contracts/GITHUB_AUTHORITY.md`
- `tests/test_github_authority_adapter.py`

## Proven invariants

- remote authority starts only from a successful immutable MASON receipt,
- MASON must still report no prior remote write/authority,
- target branch must equal the MASON base SHA at preparation,
- remote candidate branch must equal the exact MASON candidate SHA,
- explicit `GITHUB_PR_MERGE` authorization is independently bound,
- GitHub policy is observed and hashed into the plan,
- unprotected/no-rules targets fail closed,
- pull-request governance and required checks are mandatory,
- merge queue, required linear history, and required deployment policies fail as unsupported in this first slice,
- PR head/base are identity-bound,
- required checks are evaluated on the exact candidate SHA,
- required approval count is checked,
- policy/base/candidate drift blocks merge,
- merge passes expected head SHA to GitHub,
- successful authority requires target branch verification plus candidate-as-parent verification,
- remote authority receipts are immutable/idempotent durable runtime state.

## Research basis

GitHub documents that required status checks must succeed on the latest commit SHA and that protected branches/rulesets enforce reviews, checks, deployments, linear history, and merge queues. The repository rules endpoint exposes the active rules applying to a branch using metadata-read permissions. SLSA's verification guidance reinforces the same design principle: provenance/claims become meaningful only when verified against explicit expectations.

## Known boundary

`neohack2023/Dev-os` currently reports `main` as unprotected. The adapter therefore must not self-use against this repository until appropriate GitHub protection/ruleset policy exists. The slice does not create or mutate those policies.

## Deferred

- policy bootstrap/management,
- merge queue support,
- required deployment verification,
- exact-equivalence receipts for squash/rebase workflows,
- pushing/materializing a candidate branch when the exact candidate commit is not already present on GitHub,
- webhook/event-driven continuation.
