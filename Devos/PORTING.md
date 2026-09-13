# Porting DevOS into an existing repository

## Install

1. Copy the complete `Devos/` directory into the host repository root.
2. Initialize the host:

```bash
python Devos/runtime/devos.py init \
  --scope my-project \
  --repository owner/repo \
  --project-name "My Project"
```

3. Replace or extend the starter `project-core` branch with real retrieval/ownership boundaries.
4. Add bounded work to `Devos/tasks.jsonl`; record lifecycle changes in `Devos/task-events.jsonl`.
5. Validate the queue and repository:

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/devos.py validate
```

6. Build the local knowledge projection:

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py health
```

7. Generate branch-aware packets as needed:

```bash
python Devos/runtime/knowledge_runtime.py packet "search terms" --branch project-core
```

8. Admit evidence only from explicit evidence-episode JSON:

```bash
python Devos/runtime/evidence_store.py admit path/to/evidence-episode.json
```

9. Derive reflection candidates only from admitted evidence deltas:

```bash
python Devos/runtime/reflection_store.py \
  --db Devos/state/devos-knowledge.db \
  reflect --delta <delta-id> --request path/to/reflection-request.json
```

10. Wire host CI to package validation plus applicable subsystem tests/build/packet/evidence/reflection checks.

## Package-owned vs instance-owned

Package-owned files are contracts, schemas, templates, runtime code, tests, version metadata, checkpoints, and documentation.

Instance-owned files are generated for each host: `project.json`, `branches.jsonl`, `tasks.jsonl`, `task-events.jsonl`, `opportunities.jsonl`, `tools.jsonl`, `governance-lock.json`, and `research-policy.json`.

Receipts and runtime databases are host state. They must not be copied from one project into another as bootstrap defaults.

## Knowledge DB rebuild boundary

A normal knowledge DB build replaces only repository-derived projection tables and preserves durable runtime-owned state such as `runtime_kv`, evidence tables, and reflection candidates. Use `build --fresh` only when destructive reset is intended.

## Knowledge runtime boundary

Context packet generation is read-only against an existing projection. It reports source drift and does not silently rebuild stale state unless refresh is explicitly requested.

## Evidence boundary

Evidence is durable runtime state, not a projection and not authority. Do not foreign-key durable evidence to rebuildable projection tables such as `branch_state`; validate branch identity at admission instead.

Identical evidence replay is idempotent. Reusing a root or finding ID with different content is a hard conflict.

## Reflection boundary

Reflection is derived from admitted evidence deltas and remains authority-neutral.

A reflection request must:

- cite only evidence references present on its source delta,
- include at least one competing explanation,
- include a predicted consequence,
- include a required disconfirmation test,
- remain branch-scoped.

Do not treat self-generated reflection text or numeric confidence as evidence. A reflection candidate cannot mutate authority, update canon, or mark itself accepted. New evidence and governed evaluation are required before STONE -> MASON promotion can even be considered.

Reflection candidates are durable runtime state and survive normal projection rebuilds. Like evidence, they validate branch identity at admission rather than foreign-keying into rebuildable projection tables.

## Validation boundary

Normal validation checks that registered branch surfaces actually exist in the host repository. `repo_validator.py --skip-surface-checks validate` exists only for staged migrations.

## Upgrade rule

An upgrade may replace package-owned files. It must preserve instance-owned files unless an explicit migration declares and verifies a transformation.

When a subsystem schema changes, migrate host state explicitly. Never silently rewrite a project's queue, evidence, reflection, authority state, or runtime-owned database state during package upgrade.
