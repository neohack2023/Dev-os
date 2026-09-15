from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

spec_db = importlib.util.spec_from_file_location("db_runtime", ROOT / "runtime" / "db_runtime.py")
db = importlib.util.module_from_spec(spec_db)
spec_db.loader.exec_module(db)

spec_lineage = importlib.util.spec_from_file_location("knowledge_lineage", ROOT / "runtime" / "knowledge_lineage.py")
lineage = importlib.util.module_from_spec(spec_lineage)
spec_lineage.loader.exec_module(lineage)

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

    def make_persisted(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        connection = db.connect_runtime(Path(td.name) / "trajectory.db")
        self.addCleanup(connection.close)
        sid = lineage.ensure_subject(
            connection,
            scope_key="github:neohack2023/Dev-os",
            knowledge_key="runtime.python.minimum",
            knowledge_kind="semantic",
            created_at="2026-09-15T09:00:00Z",
        )
        old = lineage.append_assertion(
            connection,
            subject_id=sid,
            claim={"value": "3.10"},
            evidence_refs=["repo:old"],
            recorded_at="2026-09-15T09:01:00Z",
        )
        new = lineage.append_assertion(
            connection,
            subject_id=sid,
            claim={"value": "3.11"},
            evidence_refs=["repo:new"],
            recorded_at="2026-09-15T10:00:00Z",
        )
        edge = lineage.link_assertions(
            connection,
            relation="SUPERSEDES",
            from_assertion_id=new,
            to_assertion_id=old,
            rationale="minimum changed",
            created_at="2026-09-15T10:01:00Z",
        )
        record = trajectory.build_transition(
            subject_id=sid,
            relation="SUPERSEDES",
            from_assertion_id=new,
            to_assertion_id=old,
            reason="pyproject raised minimum Python version",
            basis_refs=["repo:pyproject.toml", "ci:portable-validation"],
            trigger_ref="commit:abc123",
            decision_ref="STONE:python-minimum",
            effective_at="2026-09-15T10:00:00Z",
            recorded_at="2026-09-15T10:02:00Z",
            metadata={"actor": "MASON"},
        )
        return connection, sid, edge, record

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

    def test_persist_transition_binds_exact_lineage_edge_and_is_idempotent(self):
        connection, _, edge, record = self.make_persisted()
        first = trajectory.persist_transition(connection, record, edge_id=edge)
        second = trajectory.persist_transition(connection, record, edge_id=edge)
        self.assertEqual(first, second)
        row = connection.execute(
            "SELECT edge_id,reason,basis_refs_json FROM knowledge_state_transitions WHERE transition_id=?",
            (first,),
        ).fetchone()
        self.assertEqual(edge, row["edge_id"])
        self.assertEqual(record["reason"], row["reason"])
        self.assertIn("repo:pyproject.toml", row["basis_refs_json"])

    def test_compact_trajectory_hides_basis_values_and_expand_restores_them(self):
        connection, sid, edge, record = self.make_persisted()
        trajectory.persist_transition(connection, record, edge_id=edge)
        compact = trajectory.compact_trajectory(connection, subject_id=sid)
        self.assertEqual(1, len(compact))
        self.assertEqual(2, compact[0]["basis_count"])
        self.assertNotIn("basis_refs", compact[0])
        expanded = trajectory.expand_trajectory(connection, subject_id=sid)
        self.assertEqual(record["basis_refs"], expanded[0]["basis_refs"])
        self.assertEqual("MASON", expanded[0]["metadata"]["actor"])

    def test_transition_rejects_wrong_edge_binding(self):
        connection, sid, _, record = self.make_persisted()
        other_old = lineage.append_assertion(
            connection,
            subject_id=sid,
            claim={"value": "3.9"},
            evidence_refs=["repo:older"],
            recorded_at="2026-09-14T10:00:00Z",
        )
        other_edge = lineage.link_assertions(
            connection,
            relation="SUPERSEDES",
            from_assertion_id=record["to_assertion_id"],
            to_assertion_id=other_old,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            trajectory.persist_transition(connection, record, edge_id=other_edge)


if __name__ == "__main__":
    unittest.main()
