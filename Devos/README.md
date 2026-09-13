# DevOS Portable Package

DevOS is repository-side development intelligence: routing, evidence boundaries, bounded research, reflection, task state, tool knowledge, governed learning, a local queryable knowledge projection, branch-aware context packets, and immutable local evidence that live with the code they serve.

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

Declarations live in `Devos/tasks.jsonl`; append-only lifecycle overlays live in `Devos/task-events.jsonl`. Selection is deterministic and host-neutral. See `contracts/TASK_QUEUE.md` and checkpoint `checkpoints/TASK_QUEUE_PORT_01.md`.

### Repository validator

```bash
python Devos/runtime/repo_validator.py validate
```

The validator checks project/governance agreement, branch topology and host surfaces, task routing, tool pinning, path safety, and local-first authority rules without requiring Notion or any other live external-memory service. `python Devos/runtime/devos.py validate` delegates initialized-instance checks to it.

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

Evidence IDs are immutable: identical replay is idempotent, while reusing an ID with changed content is rejected. Normal knowledge projection rebuilds preserve evidence. See `contracts/EVIDENCE_RUNTIME.md`, `schemas/evidence-episode.schema.json`, and checkpoint `checkpoints/EVIDENCE_RUNTIME_PORT_01.md`.

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
