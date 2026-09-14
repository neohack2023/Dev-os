# GITHUB_POLICY_BOOTSTRAP_01

Status: staged for v0.12.0

## Goal

Make the GitHub authority boundary capability-aware and verifiable before DevOS attempts governed remote promotion.

## Added

- `runtime/github_policy_bootstrap.py`
- `schemas/runtime-db-v8.sql`
- `schemas/github-policy-request.schema.json`
- `contracts/GITHUB_POLICY_BOOTSTRAP.md`
- `tests/test_github_policy_bootstrap.py`

## Runtime state

Schema v8 adds durable `github_policy_audits` and `github_policy_receipts`.

## Proven laws

- audit-only never performs an administrative write;
- apply requires explicit `GITHUB_POLICY_ADMIN` authorization;
- an unprotected branch is noncompliant;
- branch protection writes are re-read and reverified before `APPLIED`;
- stronger existing checks/review requirements are preserved without rewriting;
- active rulesets are observed but never rewritten by this portable slice;
- ruleset absence or account-tier limitations do not disable audit mode;
- policy receipts are durable runtime state and do not authorize repository mutation by themselves.

## Current proving-ground observation

At the start of this slice, `neohack2023/Dev-os` `main` was reported by GitHub as unprotected. Repository rulesets were unavailable for this private repository/account tier, so the portable design does not assume rulesets exist.

## Promotion criterion

Checkpoint is promotable only after the exact staging head passes the full portable suite plus a dedicated network-free policy bootstrap workflow, followed by the identical checks on `main`.
