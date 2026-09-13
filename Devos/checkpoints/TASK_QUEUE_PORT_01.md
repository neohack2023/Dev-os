# TASK_QUEUE_PORT_01

Status: checkpoint accepted locally

Source behavior: `neohack2023/project-orath` `tools/devos_tasks.py` at blob `1121c0bd8673c64f7446aa2296fec9998527db06`, with task queue contract at blob `b4720f9cee3d9af5375e5cf705756c5ce5869bb7`.

## Portable delta

- moved task selection/folding logic into `Devos/runtime/task_queue.py`;
- removed fixed `Project Orath` scope and `ORATH-DEV-*` identity requirements;
- removed browser-delivery coupling from task rendering/selection;
- resolved all state relative to an explicit `Devos/` root;
- standardized portable `dependencies` and `acceptance_criteria` field names;
- preserved append-only lifecycle overlays, deterministic priority ordering, branch routing, dependency gating, canary selection, evidence accumulation, and cycle rejection;
- added portable task + task-event schemas and deterministic fixture corpus.

## Local verification

- 6 unit tests pass;
- fixture queue validates: 4 declarations / 1 lifecycle event;
- normal `next` selects `DEVOS-TASK-002` after dependency completion;
- `next --canary` selects `DEVOS-TASK-003`;
- unknown branches, dependency cycles, and duplicate event IDs are rejected.

## Deferred

The richer repository validator, knowledge DB, research scout, reflection, evidence store, learning store/threshold, and diagnostic runtime remain separate neutralization slices. No raw Orath runtime state was copied into the distribution.
