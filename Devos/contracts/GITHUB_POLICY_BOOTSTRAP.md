# GitHub Policy Bootstrap Contract

`GITHUB_POLICY_BOOTSTRAP_01` defines the minimum GitHub authority guarantees required before the remote-authority adapter may treat a branch as governed.

## Required guarantees

- target branch policy is observable;
- pull requests are required;
- at least one approving review is required;
- `DevOS Portable Validation / validate` is required;
- `DevOS GitHub Authority Validation / github-authority` is required;
- the resulting policy is re-read after any administrative mutation;
- stronger existing policy is never weakened.

## Capability modes

`RULESET`: active rules are observable. The portable bootstrap audits them but does not rewrite rulesets.

`BRANCH_PROTECTION`: legacy branch protection is observable and may be created only through an explicit `GITHUB_POLICY_ADMIN` authorization.

`UNPROTECTED`: the branch has no enforceable policy. Audit mode records `BLOCKED`; apply mode may establish the minimum branch protection when the GitHub account/tier and token permit it.

`UNKNOWN`: policy cannot be proved. DevOS must fail closed.

## Authority boundary

Policy administration is distinct from MASON execution and from `GITHUB_PR_MERGE` authorization. A normal learning/promotion flow cannot grant itself administration authority.

`AUDIT_ONLY` performs no administrative write. `APPLY_AND_VERIFY` requires explicit `GITHUB_POLICY_ADMIN` authorization.

A write response is not proof. The policy must be observed again and satisfy the minimum guarantees before an `APPLIED` receipt is emitted.

Rulesets are never rewritten by this portable slice because doing so could flatten stronger repository/organization policy into the DevOS minimum. An administrator-managed ruleset must be changed through its own governance surface.

All audits and receipts are immutable durable runtime evidence. They are not project canon and do not themselves authorize repository changes.
