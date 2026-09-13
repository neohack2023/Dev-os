# Porting DevOS into an existing repository

## Install

1. Copy the complete `Devos/` directory into the host repository root.
2. Run:

```bash
python Devos/runtime/devos.py init \
  --scope my-project \
  --repository owner/repo \
  --project-name "My Project"
```

3. The starter `project-core` branch targets `"."`, so a fresh install is repository-shape neutral. Replace or extend it with real retrieval/ownership boundaries.
4. Add task declarations to `Devos/tasks.jsonl` only when bounded work should enter the local assignment surface.
5. Record lifecycle changes in `Devos/task-events.jsonl` rather than rewriting declaration history.
6. Validate queue semantics with `python Devos/runtime/task_queue.py validate`.
7. Validate the complete initialized DevOS instance with `python Devos/runtime/repo_validator.py validate` or `python Devos/runtime/devos.py validate`.
8. Wire host CI to `python Devos/runtime/devos.py validate` plus the applicable subsystem tests.
9. Add host-specific tools, authority adapters, and memory connectors through governed changes rather than editing distribution defaults ad hoc.

## Package-owned vs instance-owned

Package-owned files are contracts, schemas, templates, runtime code, tests, version metadata, checkpoints, and documentation.

Instance-owned files are generated for each host: `project.json`, `branches.jsonl`, `tasks.jsonl`, `task-events.jsonl`, `opportunities.jsonl`, `tools.jsonl`, `governance-lock.json`, and `research-policy.json`.

Receipts and runtime databases are host state. They must not be copied from one project into another as bootstrap defaults.

## Validation boundary

Normal validation checks that registered branch surfaces actually exist in the host repository. `repo_validator.py --skip-surface-checks validate` exists only for staged migrations before surfaces are materialized; it should not be the normal CI path.

## Upgrade rule

An upgrade may replace package-owned files. It must preserve instance-owned files unless an explicit migration declares and verifies a transformation.

When a subsystem schema changes, migrate host state explicitly. Never silently rewrite a project's queue, evidence, or authority state during package upgrade.
