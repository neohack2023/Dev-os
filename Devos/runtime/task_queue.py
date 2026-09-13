#!/usr/bin/env python3
"""Portable DevOS task queue runtime.

This module is intentionally host-neutral. It reads queue state from one Devos/
instance, validates deterministic routing/dependency rules, folds lifecycle events,
and selects the next assignable task. Queue state never authorizes work by itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

DEVOS_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_STATUS = {
    "READY",
    "BLOCKED",
    "TRACKING",
    "CLAIMED",
    "IN_PROGRESS",
    "VERIFY",
    "DONE",
    "PAUSED",
    "REJECTED",
    "CANCELLED",
}
ALLOWED_TASK_TYPES = {
    "repository_execution",
    "feature_incubation",
    "quality_assurance",
    "research",
    "cross_branch_architecture",
    "devos_self_improvement",
}
REQUIRED_TASK_FIELDS = {
    "task_id",
    "title",
    "priority",
    "status",
    "branch_keys",
    "task_type",
    "owner_role",
    "assigned_agent",
    "dependencies",
    "tracking",
    "objective",
    "acceptance_criteria",
    "transfer_canary",
    "evidence_refs",
}
REQUIRED_EVENT_FIELDS = {"event_id", "task_id", "status", "occurred_on"}


def _load_jsonl(path: Path, *, label: str) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on {label} line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{label} line {line_no} must be a JSON object")
        rows.append(row)
    return rows


def _nonempty_strings(values: object) -> bool:
    return isinstance(values, list) and all(isinstance(item, str) and item.strip() for item in values)


def load_branch_keys(path: Path) -> set[str]:
    rows = _load_jsonl(path, label="branch")
    keys: list[str] = []
    for line_no, row in enumerate(rows, 1):
        key = row.get("branch_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"branch line {line_no} has invalid branch_key")
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError("branch keys must be unique")
    return set(keys)


def load_task_declarations(path: Path) -> list[dict]:
    return _load_jsonl(path, label="task")


def load_task_events(path: Path) -> list[dict]:
    events = _load_jsonl(path, label="task event")
    seen: set[str] = set()
    for line_no, event in enumerate(events, 1):
        missing = sorted(REQUIRED_EVENT_FIELDS - set(event))
        if missing:
            raise ValueError(f"task event line {line_no} missing fields: {', '.join(missing)}")
        event_id = event["event_id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"task event line {line_no} has invalid event_id")
        if event_id in seen:
            raise ValueError(f"duplicate task event id: {event_id}")
        seen.add(event_id)
        if event["status"] not in ALLOWED_STATUS:
            raise ValueError(f"{event_id}: invalid status {event['status']}")
        for field in ("tracking_add", "evidence_refs_add"):
            values = event.get(field, [])
            if not _nonempty_strings(values):
                raise ValueError(f"{event_id}: {field} must be a list of non-empty strings")
        if "assigned_agent" in event and event["assigned_agent"] is not None:
            if not isinstance(event["assigned_agent"], str) or not event["assigned_agent"].strip():
                raise ValueError(f"{event_id}: assigned_agent must be null or a non-empty string")
    return events


def validate_task_declarations(tasks: list[dict], branch_keys: set[str] | None = None) -> None:
    ids: list[str] = []
    for line_no, task in enumerate(tasks, 1):
        missing = sorted(REQUIRED_TASK_FIELDS - set(task))
        extra = sorted(set(task) - REQUIRED_TASK_FIELDS)
        if missing:
            raise ValueError(f"task line {line_no} missing fields: {', '.join(missing)}")
        if extra:
            raise ValueError(f"task line {line_no} extra fields: {', '.join(extra)}")

        task_id = task["task_id"]
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(f"task line {line_no} has invalid task_id")
        ids.append(task_id)

        if not isinstance(task["priority"], int) or isinstance(task["priority"], bool) or task["priority"] <= 0:
            raise ValueError(f"{task_id}: priority must be a positive integer")
        if task["status"] not in ALLOWED_STATUS:
            raise ValueError(f"{task_id}: invalid status {task['status']}")
        if task["task_type"] not in ALLOWED_TASK_TYPES:
            raise ValueError(f"{task_id}: invalid task_type {task['task_type']}")
        for field in ("title", "owner_role", "objective"):
            if not isinstance(task[field], str) or not task[field].strip():
                raise ValueError(f"{task_id}: {field} must be a non-empty string")
        if task["assigned_agent"] is not None and (
            not isinstance(task["assigned_agent"], str) or not task["assigned_agent"].strip()
        ):
            raise ValueError(f"{task_id}: assigned_agent must be null or a non-empty string")
        for field in ("branch_keys", "dependencies", "tracking", "acceptance_criteria", "evidence_refs"):
            if not _nonempty_strings(task[field]):
                raise ValueError(f"{task_id}: {field} must be a list of non-empty strings")
        if not task["branch_keys"]:
            raise ValueError(f"{task_id}: branch_keys must not be empty")
        if not task["acceptance_criteria"]:
            raise ValueError(f"{task_id}: acceptance_criteria must not be empty")
        if not isinstance(task["transfer_canary"], bool):
            raise ValueError(f"{task_id}: transfer_canary must be boolean")
        if task["status"] == "READY" and task["assigned_agent"] is not None:
            raise ValueError(f"{task_id}: READY task must be unassigned")
        if task["status"] == "BLOCKED" and not task["dependencies"]:
            raise ValueError(f"{task_id}: BLOCKED task must name dependencies")
        if branch_keys is not None:
            unknown = sorted(set(task["branch_keys"]) - branch_keys)
            if unknown:
                raise ValueError(f"{task_id}: unknown branch key(s): {', '.join(unknown)}")

    if len(ids) != len(set(ids)):
        raise ValueError("task ids must be unique")

    index = {task["task_id"]: task for task in tasks}
    for task in tasks:
        for dep in task["dependencies"]:
            if dep not in index:
                raise ValueError(f"{task['task_id']}: unknown dependency {dep}")
            if dep == task["task_id"]:
                raise ValueError(f"{task['task_id']}: task cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise ValueError(f"dependency cycle at {task_id}")
        visiting.add(task_id)
        for dep in index[task_id]["dependencies"]:
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)


def fold_task_events(tasks: list[dict], events: list[dict]) -> list[dict]:
    effective = {task["task_id"]: dict(task) for task in tasks}
    for task in effective.values():
        task["tracking"] = list(task.get("tracking", []))
        task["evidence_refs"] = list(task.get("evidence_refs", []))

    for event in events:
        task_id = event["task_id"]
        if task_id not in effective:
            raise ValueError(f"{event['event_id']}: unknown task_id {task_id}")
        task = effective[task_id]
        task["status"] = event["status"]
        if "assigned_agent" in event:
            task["assigned_agent"] = event["assigned_agent"]
        for field, event_field in (("tracking", "tracking_add"), ("evidence_refs", "evidence_refs_add")):
            for value in event.get(event_field, []):
                if value not in task[field]:
                    task[field].append(value)
        task["latest_lifecycle_event"] = event["event_id"]
        task["lifecycle_occurred_on"] = event["occurred_on"]
    return [effective[task["task_id"]] for task in tasks]


def load_tasks(task_path: Path, event_path: Path | None = None, branch_path: Path | None = None) -> list[dict]:
    tasks = load_task_declarations(task_path)
    branch_keys = load_branch_keys(branch_path) if branch_path is not None else None
    validate_task_declarations(tasks, branch_keys)
    if event_path is None:
        return tasks
    events = load_task_events(event_path)
    return fold_task_events(tasks, events)


def task_index(tasks: Iterable[dict]) -> dict[str, dict]:
    return {task["task_id"]: task for task in tasks}


def dependencies_done(task: dict, index: dict[str, dict]) -> bool:
    return all(index[dep]["status"] == "DONE" for dep in task.get("dependencies", []))


def assignable(tasks: list[dict]) -> list[dict]:
    index = task_index(tasks)
    ready = [
        task
        for task in tasks
        if task["status"] == "READY"
        and task.get("assigned_agent") is None
        and dependencies_done(task, index)
    ]
    return sorted(ready, key=lambda task: (task["priority"], task["task_id"]))


def render_task(task: dict) -> str:
    deps = ",".join(task["dependencies"]) if task["dependencies"] else "none"
    branches = ",".join(task["branch_keys"])
    assignee = task["assigned_agent"] or "unassigned"
    canary = "yes" if task["transfer_canary"] else "no"
    lifecycle = task.get("latest_lifecycle_event", "declaration")
    return (
        f"{task['task_id']}  P{task['priority']}  {task['status']}  {task['title']}\n"
        f"  branches={branches} assignee={assignee} dependencies={deps} transfer_canary={canary}\n"
        f"  lifecycle={lifecycle}\n"
        f"  objective={task['objective']}"
    )


def validate_instance_queue(devos_root: Path) -> tuple[int, int]:
    task_path = devos_root / "tasks.jsonl"
    event_path = devos_root / "task-events.jsonl"
    branch_path = devos_root / "branches.jsonl"
    tasks = load_task_declarations(task_path)
    branch_keys = load_branch_keys(branch_path)
    validate_task_declarations(tasks, branch_keys)
    events = load_task_events(event_path)
    fold_task_events(tasks, events)
    return len(tasks), len(events)


def _paths(devos_root: Path) -> tuple[Path, Path, Path]:
    return (
        devos_root / "tasks.jsonl",
        devos_root / "task-events.jsonl",
        devos_root / "branches.jsonl",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list effective queue entries")
    list_parser.add_argument("--status", choices=sorted(ALLOWED_STATUS))
    list_parser.add_argument("--canary", action="store_true")

    next_parser = sub.add_parser("next", help="show highest-priority assignable task")
    next_parser.add_argument("--canary", action="store_true")

    show_parser = sub.add_parser("show", help="show one effective task as JSON")
    show_parser.add_argument("task_id")

    sub.add_parser("validate", help="validate task declarations, events, branch routes, and dependency graph")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.devos_root.resolve()
    task_path, event_path, branch_path = _paths(root)
    try:
        if args.command == "validate":
            task_count, event_count = validate_instance_queue(root)
            print(json.dumps({"ok": True, "tasks": task_count, "events": event_count}, indent=2, sort_keys=True))
            return 0

        tasks = load_tasks(task_path, event_path, branch_path)
        if args.command == "list":
            selected = tasks
            if args.status:
                selected = [task for task in selected if task["status"] == args.status]
            if args.canary:
                selected = [task for task in selected if task["transfer_canary"]]
            for task in sorted(selected, key=lambda row: (row["priority"], row["task_id"])):
                print(render_task(task))
            return 0

        if args.command == "next":
            candidates = assignable(tasks)
            if args.canary:
                candidates = [task for task in candidates if task["transfer_canary"]]
            if not candidates:
                print("NO_ASSIGNABLE_TASK")
                return 1
            print(render_task(candidates[0]))
            return 0

        if args.command == "show":
            task = task_index(tasks).get(args.task_id)
            if task is None:
                print(f"UNKNOWN_TASK {args.task_id}")
                return 1
            print(json.dumps(task, indent=2, sort_keys=True))
            return 0

        raise AssertionError(args.command)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
