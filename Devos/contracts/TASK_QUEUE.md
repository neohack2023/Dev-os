# Portable Task Queue Contract

`Devos/tasks.jsonl` is the repository-local declaration surface for bounded development work. `Devos/task-events.jsonl` is the append-only lifecycle overlay. Neither authorizes work by itself.

## Canonical task row

Every declaration uses exactly these fields:

- `task_id`: stable host-defined identity. DevOS does not impose a project prefix.
- `title`: compact developer-facing title.
- `priority`: positive integer; lower sorts first.
- `status`: `READY`, `BLOCKED`, `TRACKING`, `CLAIMED`, `IN_PROGRESS`, `VERIFY`, `DONE`, `PAUSED`, `REJECTED`, or `CANCELLED`.
- `branch_keys`: one or more keys from `Devos/branches.jsonl`.
- `task_type`: `repository_execution`, `feature_incubation`, `quality_assurance`, `research`, `cross_branch_architecture`, or `devos_self_improvement`.
- `owner_role`: routing owner.
- `assigned_agent`: null until claimed, otherwise a host agent/role identifier.
- `dependencies`: task IDs that must be `DONE` before normal assignment.
- `tracking`: issue/PR/work-item references.
- `objective`: bounded outcome.
- `acceptance_criteria`: deterministic or inspectable completion criteria.
- `transfer_canary`: whether execution is intentionally useful as transfer evidence.
- `evidence_refs`: provenance/evidence pointers.

Unknown fields are rejected so queue semantics cannot drift silently.

## Lifecycle events

Events require `event_id`, `task_id`, `status`, and `occurred_on`. They may also set `assigned_agent` and append `tracking_add` or `evidence_refs_add`.

Events are folded in file order over immutable declarations. Event IDs must be unique and every event must target a declared task. This keeps task intent stable while lifecycle history remains inspectable.

## Assignment law

A task is assignable only when:

1. `status == READY` after event folding;
2. `assigned_agent` is null;
3. every declared dependency is `DONE` after event folding;
4. every `branch_key` resolves in `Devos/branches.jsonl`.

Dependency cycles, self-dependencies, and unknown dependencies are invalid. `BLOCKED` declarations must name at least one dependency. `READY` declarations must be unassigned.

`next` sorts deterministically by numeric priority then `task_id`. `--canary` filters the same candidate set; it does not grant extra authority.

## Completion law

`DONE` means the host has evidence for the declared acceptance criteria. DevOS may record and retrieve that evidence, but passing the queue gate does not itself promote knowledge, merge code, or rewrite authority. Durable learning still routes through STONE → MASON and normal repository review.

## Runtime

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/task_queue.py list
python Devos/runtime/task_queue.py next
python Devos/runtime/task_queue.py next --canary
python Devos/runtime/task_queue.py show <task-id>
```
