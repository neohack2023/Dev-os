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
8. Build the local knowledge projection when fast repo-local retrieval is useful:

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py query "search terms"
python Devos/runtime/build_knowledge_db.py health
```

9. Generate branch-aware packets for agents:

```bash
python Devos/runtime/knowledge_runtime.py status
python Devos/runtime/knowledge_runtime.py packet "search terms" --branch project-core
```

Add repeated `--branch` flags when a task legitimately crosses branch boundaries. The runtime resolves dependencies automatically. Use `--refresh` only when you intentionally want to rebuild an existing projection before retrieval.

10. Wire host CI to `python Devos/runtime/devos.py validate` plus the applicable subsystem tests/build/packet checks.
11. Add host-specific tools, authority adapters, and memory connectors through governed changes rather than editing distribution defaults ad hoc.

## Package-owned vs instance-owned

Package-owned files are contracts, schemas, templates, runtime code, tests, version metadata, checkpoints, and documentation.

Instance-owned files are generated for each host: `project.json`, `branches.jsonl`, `tasks.jsonl`, `task-events.jsonl`, `opportunities.jsonl`, `tools.jsonl`, `governance-lock.json`, and `research-policy.json`.

Receipts and runtime databases are host state. They must not be copied from one project into another as bootstrap defaults. The default SQLite path is `Devos/state/devos-knowledge.db`; the package `.gitignore` excludes the database plus WAL/SHM sidecars.

## Knowledge DB rebuild boundary

A normal knowledge DB build replaces only repository-derived projection tables and preserves runtime-owned tables such as `runtime_kv`. Use `build --fresh` only when destructive reset is intended. The logical `projection_digest` is the determinism signal; SQLite file bytes and WAL layout are not treated as canonical artifacts.

## Knowledge runtime boundary

Context packet generation is read-only against an existing projection. It reports source drift through `projection.fresh` and `changed_sources`; it does not silently rebuild stale state. A missing database may be generated because no prior projection exists. Pass `--refresh` explicitly to rebuild an existing database before packet generation.

Packets are bounded retrieval products, not authority objects. Their source manifest and packet hash make the selected context auditable, but authority remains with the checked-in repository sources.

## Validation boundary

Normal validation checks that registered branch surfaces actually exist in the host repository. `repo_validator.py --skip-surface-checks validate` exists only for staged migrations before surfaces are materialized; it should not be the normal CI path.

## Upgrade rule

An upgrade may replace package-owned files. It must preserve instance-owned files unless an explicit migration declares and verifies a transformation.

When a subsystem schema changes, migrate host state explicitly. Never silently rewrite a project's queue, evidence, authority state, or runtime-owned database state during package upgrade.
