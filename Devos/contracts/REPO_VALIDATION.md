# Repository Validation Contract

`runtime/repo_validator.py` is the portable DevOS integrity gate for one initialized host repository.

It validates repository-local structure without requiring live external memory and without encoding a particular project, branch name, product runtime, or external-memory provider.

## Required invariants

- `project.json` has a portable scope slug, `owner/repo` repository identity, explicit authority split, and canonical `Devos/` paths.
- `governance-lock.json` matches the project scope/repository and never requires live external memory for ordinary repository work.
- knowledge branches have unique keys, valid statuses, safe host-relative surfaces, resolvable dependencies, and no dependency cycles.
- task declarations/events pass the portable task-queue validator and resolve only registered branches.
- an empty tool registry is valid; populated tool entries require pinned full commit SHAs, maturity, capability qualification, limits, entrypoints, evidence, and verification date.
- installed DevOS version and instance `devos_version` must agree.
- path validation rejects absolute or parent-escaping paths.

## Authority boundary

Validation proves structural consistency, not canon, product correctness, task authorization, or external-memory freshness. Repository execution facts remain repository authority. External memory may be configured by a host but is never a prerequisite for normal local validation.

## Commands

```bash
python Devos/runtime/repo_validator.py validate
python Devos/runtime/devos.py validate
```

Use `--skip-surface-checks` only for staging/migration diagnostics where host surfaces have not yet been materialized. Do not use it as a normal CI setting.
