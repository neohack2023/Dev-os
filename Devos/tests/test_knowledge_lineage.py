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


class KnowledgeLineageTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.db_path = Path(self.td.name) / "lineage.db"
        self.connection = db.connect_runtime(self.db_path)

    def tearDown(self):
        self.connection.close()
        self.td.cleanup()

    def subject(self):
        return lineage.ensure_subject(
            self.connection,
            scope_key="github:neohack2023/Dev-os",
            knowledge_key="runtime.python.minimum",
            knowledge_kind="semantic",
            created_at="2026-09-14T10:00:00Z",
        )

    def assertion(self, sid, claim, when):
        return lineage.append_assertion(
            self.connection,
            subject_id=sid,
            claim=claim,
            evidence_refs=["repo:pyproject.toml"],
            recorded_at=when,
        )

    def test_schema_v10_is_current(self):
        health = db.runtime_health(self.connection)
        self.assertEqual(10, health["schema_version"])
        self.assertEqual(10, health["user_version"])

    def test_stable_subject_identity_is_deterministic_and_kind_locked(self):
        sid1 = self.subject()
        sid2 = self.subject()
        self.assertEqual(sid1, sid2)
        with self.assertRaisesRegex(ValueError, "cannot change knowledge_kind"):
            lineage.ensure_subject(
                self.connection,
                scope_key="github:neohack2023/Dev-os",
                knowledge_key="runtime.python.minimum",
                knowledge_kind="procedural",
            )

    def test_confirms_requires_same_canonical_claim_and_increases_support(self):
        sid = self.subject()
        a1 = self.assertion(sid, {"value": "3.11"}, "2026-09-14T10:01:00Z")
        a2 = lineage.append_assertion(
            self.connection,
            subject_id=sid,
            claim={"value": "3.11"},
            evidence_refs=["ci:portable-validation"],
            recorded_at="2026-09-14T10:02:00Z",
        )
        lineage.link_assertions(
            self.connection,
            relation="CONFIRMS",
            from_assertion_id=a2,
            to_assertion_id=a1,
            created_at="2026-09-14T10:03:00Z",
        )
        state = lineage.current_state(self.connection, subject_id=sid)
        self.assertEqual("ACTIVE", state["status"])
        self.assertEqual(1, len(state["claims"]))
        self.assertEqual(2, state["claims"][0]["support_count"])

    def test_supersedes_retires_old_assertion_without_deleting_history(self):
        sid = self.subject()
        old = self.assertion(sid, {"value": "3.10"}, "2026-09-14T10:01:00Z")
        new = self.assertion(sid, {"value": "3.11"}, "2026-09-14T10:02:00Z")
        lineage.link_assertions(
            self.connection,
            relation="SUPERSEDES",
            from_assertion_id=new,
            to_assertion_id=old,
            rationale="pyproject raised minimum",
            created_at="2026-09-14T10:03:00Z",
        )
        state = lineage.current_state(self.connection, subject_id=sid)
        self.assertEqual("ACTIVE", state["status"])
        self.assertEqual({"value": "3.11"}, state["claims"][0]["claim"])
        count = self.connection.execute("SELECT count(*) FROM knowledge_assertions").fetchone()[0]
        self.assertEqual(2, count)

    def test_conflicting_current_claims_are_contested_not_silently_ranked(self):
        sid = self.subject()
        a1 = self.assertion(sid, {"value": "3.11"}, "2026-09-14T10:01:00Z")
        a2 = self.assertion(sid, {"value": "3.12"}, "2026-09-14T10:02:00Z")
        lineage.link_assertions(
            self.connection,
            relation="CONFLICTS",
            from_assertion_id=a2,
            to_assertion_id=a1,
            rationale="repo and external documentation disagree",
            created_at="2026-09-14T10:03:00Z",
        )
        state = lineage.current_state(self.connection, subject_id=sid)
        self.assertEqual("CONTESTED", state["status"])
        self.assertEqual(2, len(state["claims"]))

    def test_relations_cannot_cross_subject_identity(self):
        sid1 = self.subject()
        sid2 = lineage.ensure_subject(
            self.connection,
            scope_key="github:neohack2023/Dev-os",
            knowledge_key="runtime.node.minimum",
            knowledge_kind="semantic",
        )
        a1 = self.assertion(sid1, {"value": "3.11"}, "2026-09-14T10:01:00Z")
        a2 = self.assertion(sid2, {"value": "22"}, "2026-09-14T10:02:00Z")
        with self.assertRaisesRegex(ValueError, "cannot cross stable knowledge identities"):
            lineage.link_assertions(
                self.connection,
                relation="CONFLICTS",
                from_assertion_id=a2,
                to_assertion_id=a1,
            )

    def test_supersedes_cycle_is_rejected(self):
        sid = self.subject()
        a1 = self.assertion(sid, {"value": "3.10"}, "2026-09-14T10:01:00Z")
        a2 = self.assertion(sid, {"value": "3.11"}, "2026-09-14T10:02:00Z")
        a3 = self.assertion(sid, {"value": "3.12"}, "2026-09-14T10:03:00Z")
        lineage.link_assertions(self.connection, relation="SUPERSEDES", from_assertion_id=a2, to_assertion_id=a1)
        lineage.link_assertions(self.connection, relation="SUPERSEDES", from_assertion_id=a3, to_assertion_id=a2)
        with self.assertRaisesRegex(ValueError, "cycle"):
            lineage.link_assertions(self.connection, relation="SUPERSEDES", from_assertion_id=a1, to_assertion_id=a3)

    def test_relation_semantics_are_deterministic(self):
        sid = self.subject()
        a1 = self.assertion(sid, {"value": "3.11"}, "2026-09-14T10:01:00Z")
        a2 = self.assertion(sid, {"value": "3.12"}, "2026-09-14T10:02:00Z")
        a3 = lineage.append_assertion(
            self.connection,
            subject_id=sid,
            claim={"value": "3.11"},
            evidence_refs=["ci:portable-validation"],
            recorded_at="2026-09-14T10:03:00Z",
        )
        with self.assertRaisesRegex(ValueError, "CONFIRMS requires identical"):
            lineage.link_assertions(self.connection, relation="CONFIRMS", from_assertion_id=a2, to_assertion_id=a1)
        with self.assertRaisesRegex(ValueError, "SUPERSEDES requires different"):
            lineage.link_assertions(self.connection, relation="SUPERSEDES", from_assertion_id=a3, to_assertion_id=a1)
        with self.assertRaisesRegex(ValueError, "CONFLICTS requires different"):
            lineage.link_assertions(self.connection, relation="CONFLICTS", from_assertion_id=a3, to_assertion_id=a1)


if __name__ == "__main__":
    unittest.main()
