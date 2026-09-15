from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("knowledge_trajectory", ROOT / "runtime" / "knowledge_trajectory.py")
trajectory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trajectory)


class KnowledgeTrajectoryTests(unittest.TestCase):
    def record(self, **overrides):
        values = {
            "subject_id": "ks_aaaaaaaaaaaaaaaaaaaaaaaa",
            "relation": "SUPERSEDES",
            "from_assertion_id": "ka_bbbbbbbbbbbbbbbbbbbbbbbb",
            "to_assertion_id": "ka_cccccccccccccccccccccccc",
            "reason": "repository minimum Python version changed",
            "basis_refs": ["repo:pyproject.toml", "ci:portable-validation"],
            "effective_at": "2026-09-15T10:00:00Z",
            "recorded_at": "2026-09-15T10:05:00Z",
        }
        values.update(overrides)
        return trajectory.build_transition(**values)

    def test_transition_requires_reason_and_basis(self):
        with self.assertRaisesRegex(ValueError, "reason"):
            self.record(reason="")
        with self.assertRaisesRegex(ValueError, "basis_refs"):
            self.record(basis_refs=[])

    def test_transition_id_is_deterministic(self):
        first = self.record()
        second = self.record(basis_refs=["ci:portable-validation", "repo:pyproject.toml"])
        self.assertEqual(first["transition_id"], second["transition_id"])

    def test_assertion_semantics_are_checked_when_available(self):
        record = self.record()
        assertions = {
            record["from_assertion_id"]: {
                "subject_id": record["subject_id"],
                "claim_hash": "new",
            },
            record["to_assertion_id"]: {
                "subject_id": record["subject_id"],
                "claim_hash": "old",
            },
        }
        trajectory.validate_transition(record, assertions=assertions)
        assertions[record["to_assertion_id"]]["claim_hash"] = "new"
        with self.assertRaisesRegex(ValueError, "different claim hashes"):
            trajectory.validate_transition(record, assertions=assertions)

    def test_transition_must_match_lineage_edge(self):
        record = self.record()
        edge = {
            "subject_id": record["subject_id"],
            "relation": record["relation"],
            "from_assertion_id": record["from_assertion_id"],
            "to_assertion_id": record["to_assertion_id"],
        }
        trajectory.validate_transition(record, edge=edge)
        edge["relation"] = "CONFLICTS"
        with self.assertRaisesRegex(ValueError, "relation"):
            trajectory.validate_transition(record, edge=edge)

    def test_trajectory_orders_effective_then_recorded_time(self):
        later = self.record(
            from_assertion_id="ka_dddddddddddddddddddddddd",
            to_assertion_id="ka_bbbbbbbbbbbbbbbbbbbbbbbb",
            reason="second revision",
            basis_refs=["repo:commit:2"],
            effective_at="2026-09-16T10:00:00Z",
            recorded_at="2026-09-16T10:01:00Z",
        )
        earlier = self.record(
            basis_refs=["repo:commit:1"],
            effective_at="2026-09-15T10:00:00Z",
            recorded_at="2026-09-15T10:01:00Z",
        )
        ordered = trajectory.trajectory([later, earlier], subject_id=earlier["subject_id"])
        self.assertEqual([earlier["transition_id"], later["transition_id"]], [row["transition_id"] for row in ordered])


if __name__ == "__main__":
    unittest.main()
