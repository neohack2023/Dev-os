# DevOS Portable Package

DevOS is repository-side development intelligence: routing, evidence boundaries, bounded research, reflection, task state, tool knowledge, governed learning, a local queryable knowledge projection, branch-aware context packets, immutable local evidence, and evidence-bounded reflection candidates that live with the code they serve.

Everything owned by the package lives under `Devos/` so the folder can be copied into another repository intact.

Initialize a host repository with:

```bash
python Devos/runtime/devos.py init --scope my-project --repository owner/repo --project-name "My Project"
python Devos/runtime/devos.py validate
```

The distribution ships no host task history, receipts, sync history, runtime database, or project canon. Those are generated per repository.

## Portable executable subsystems

### Task queue

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/task_queue.py next
python Devos/runtime/task_queue.py next --canary
python Devos/runtime/task_queue.py show <task-id>
```

Declarations live in `Devos/tasks.jsonl`; append-only lifecycle overlays live in `Devos/task-events.jsonl`. Selection is deterministic and host-neutral.

### Repository validator

```bash
python Devos/runtime/repo_validator.py validate
```

The validator checks project/governance agreement, branch topology and host surfaces, task routing, tool pinning, path safety, and local-first authority rules without requiring live external memory.

### Knowledge database

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py query "search terms"
python Devos/runtime/build_knowledge_db.py health
```

The default database is `Devos/state/devos-knowledge.db`. Normal rebuilds refresh repository-derived projection tables while preserving durable runtime state. `build --fresh` is the explicit destructive reset.

### Knowledge runtime

```bash
python Devos/runtime/knowledge_runtime.py status
python Devos/runtime/knowledge_runtime.py packet "search terms" --branch project-core
```

The runtime turns the SQLite projection into bounded branch-aware context packets with deterministic ranking, provenance, staleness reporting, and packet hashes.

### Evidence runtime

```bash
python Devos/runtime/evidence_store.py admit path/to/evidence-episode.json
python Devos/runtime/evidence_store.py list
python Devos/runtime/evidence_store.py list --branch project-core
```

Evidence roots and atomic findings are admitted as durable SQLite state. Lineage collapse prevents derivatives and same-input reproductions from inflating independent support. Explicit cross-reference and triangulation produce review-oriented delta packets whose `authority_effect` is always `NONE`.

Evidence IDs are immutable: identical replay is idempotent, while reusing an ID with changed content is rejected. Normal knowledge projection rebuilds preserve evidence.

### Reflection core

```bash
python Devos/runtime/reflection_store.py --db Devos/state/devos-knowledge.db \
  reflect --delta <delta-id> --request path/to/reflection-request.json

python Devos/runtime/reflection_store.py --db Devos/state/devos-knowledge.db \
  list --branch project-core
```

Reflection starts from an admitted evidence delta. The request must cite evidence already present on that delta, provide a competing explanation, predict a consequence, and define a disconfirmation test.

Reflection candidates are deterministic, immutable/idempotent durable runtime state. They remain `CANDIDATE_ONLY` with `authority_effect: NONE`. Competing hypotheses over the same delta remain distinct candidates. Reflective prose cannot promote itself or manufacture evidence.

See `contracts/REFLECTION_CORE.md`, `schemas/reflection-request.schema.json`, and checkpoint `checkpoints/REFLECTION_CORE_PORT_01.md`.

## Core law

- GitHub owns live repository execution truth.
- External memory is optional and configured by the host.
- STONE controls evidence intake and provenance.
- MASON controls durable assembly and verified writes.
- Research is bounded and need-triggered.
- Reflection may nominate improvements but cannot self-promote them.
- Repetition/prevalence never upgrades authority by itself.
- Ordinary repo work must remain possible from the checked-in local bundle.

See `PORTING.md` for installation and upgrade boundaries.
