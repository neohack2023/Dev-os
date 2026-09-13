from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "task_queue"
spec = importlib.util.spec_from_file_location("task_queue", ROOT / "runtime" / "task_queue.py")
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class PortableTaskQueueTests(unittest.TestCase):
    def load(self):
        return queue.load_tasks(FIX / "tasks.jsonl", FIX / "task-events.jsonl", FIX / "branches.jsonl")

    def test_fixture_validates_and_folds_events(self):
        tasks = self.load()
        by_id = {task["task_id"]: task for task in tasks}
        self.assertEqual("DONE", by_id["DEVOS-TASK-001"]["status"])
        self.assertEqual("FIXTURE-AGENT", by_id["DEVOS-TASK-001"]["assigned_agent"])
        self.assertIn("fixture:test-pass", by_id["DEVOS-TASK-001"]["evidence_refs"])

    def test_dependency_completion_releases_next_task(self):
        tasks = self.load()
        ids = [task["task_id"] for task in queue.assignable(tasks)]
        self.assertEqual(["DEVOS-TASK-002", "DEVOS-TASK-003"], ids)

    def test_canary_selection_is_host_neutral(self):
        candidates = [task for task in queue.assignable(self.load()) if task["transfer_canary"]]
        self.assertEqual("DEVOS-TASK-003", candidates[0]["task_id"])

    def test_unknown_branch_is_rejected(self):
        rows = queue.load_task_declarations(FIX / "tasks.jsonl")
        rows[0] = dict(rows[0])
        rows[0]["branch_keys"] = ["missing-branch"]
        with self.assertRaisesRegex(ValueError, "unknown branch"):
            queue.validate_task_declarations(rows, queue.load_branch_keys(FIX / "branches.jsonl"))

    def test_dependency_cycle_is_rejected(self):
        rows = queue.load_task_declarations(FIX / "tasks.jsonl")
        rows = [dict(row) for row in rows]
        rows[0]["dependencies"] = ["DEVOS-TASK-002"]
        rows[1]["dependencies"] = ["DEVOS-TASK-001"]
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            queue.validate_task_declarations(rows, queue.load_branch_keys(FIX / "branches.jsonl"))

    def test_duplicate_event_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            event = json.loads((FIX / "task-events.jsonl").read_text().strip())
            path.write_text(json.dumps(event) + "\n" + json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate task event id"):
                queue.load_task_events(path)


if __name__ == "__main__":
    unittest.main()
