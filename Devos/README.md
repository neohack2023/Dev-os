# DevOS Portable Package

DevOS is repository-side development intelligence: routing, evidence boundaries, bounded research, reflection, task state, tool knowledge, and governed learning that live with the code they serve.

Everything owned by the package lives under `Devos/` so the folder can be copied into another repository intact.

Initialize a host repository with:

```bash
python Devos/runtime/devos.py init --scope my-project --repository owner/repo --project-name "My Project"
python Devos/runtime/devos.py validate
```

The distribution ships no host task history, receipts, sync history, or project canon. Those are generated per repository.

## Portable executable subsystems

### Task queue

The first extracted executable subsystem is the portable task queue:

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/task_queue.py next
python Devos/runtime/task_queue.py next --canary
python Devos/runtime/task_queue.py show <task-id>
```

Declarations live in `Devos/tasks.jsonl`; append-only lifecycle overlays live in `Devos/task-events.jsonl`. Selection is deterministic and host-neutral. See `contracts/TASK_QUEUE.md` and checkpoint `checkpoints/TASK_QUEUE_PORT_01.md`.

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
