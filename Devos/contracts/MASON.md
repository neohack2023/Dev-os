# MASON Assembly Contract

MASON consumes a locked STONE package when durable knowledge may change. It decides what surviving material becomes, where it belongs, whether it is strong enough to promote, how it is written, and how the write is verified.

Preserve authority labels separately from freshness, usefulness, confidence, and prevalence.

Repository-accepted operating knowledge may be promoted through normal reviewed repository changes plus tests/CI. External project memory remains governed by the host's configured authority. A repo agent may prepare a bounded sync delta but must not claim an upstream write occurred unless it was actually executed and verified.

Every durable mutation plan names the source STONE manifest, exact target, exact delta, authority effect, preconditions, destination authority, rollback/failure behavior, verification method, and required authorization.

A promotion-gate result of `PROMOTE` means only that the candidate satisfied the configured verifier gates and is eligible for MASON review. It never means a push, merge, deploy, or canon write has been authorized. MASON must bind any execution attempt to the same candidate revision and change digest, respect repository protection/review policy, and verify the resulting repository state independently.

`MASON_EXECUTION_PORT_01` defines the first executable mutation surface. It is intentionally local-only: an explicitly authorized plan may advance the current local target branch from an exact base revision to the exact reviewed candidate with `git merge --ff-only`. Preparation and post-write verification must both prove candidate ancestry, bounded changed paths, canonical diff digest, branch identity, and clean worktree state. The executor cannot generate source changes, apply arbitrary patches, run candidate-provided commands, force/reset a branch, or push to a remote.

A successful local execution receipt may record `local_authority_effect: LOCAL_GIT_REF_UPDATED`, but it must record `remote_authority_effect: NONE` and `remote_write_performed: false`. GitHub or another remote repository remains a separate authority boundary governed by its own review, status-check, ruleset, deployment, and merge controls.

A `ROLLBACK` classification likewise requires a MASON rollback plan and execution receipt; the promotion gate does not perform the rollback itself. The local fast-forward executor records the prior revision as a rollback target but does not automatically rewrite branch history backward.

A no-op durable result is valid. One execution attempt should produce one immutable receipt after writes stop and independent verification completes.
