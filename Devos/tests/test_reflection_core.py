from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from build_knowledge_db import build
from db_runtime import CURRENT_SCHEMA_VERSION, connect_runtime
from evidence_store import persist_episode
from reflection_core import build_reflection_core
from reflection_store import persist_reflection, list_reflections

HOST_FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"
EVIDENCE_FIXTURE = ROOT / "tests" / "fixtures" / "evidence" / "episode-convergence.json"
REQUEST_FIXTURE = ROOT / "tests" / "fixtures" / "reflection" / "request-lantern.json"


class ReflectionCoreTests(unittest.TestCase):
    def test_core_is_deterministic_and_authority_neutral(self):
        request = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
        kwargs = dict(
            source_kind="EVIDENCE_DELTA",
            source_id="delta-example",
            source_digest="sha256:" + "a" * 64,
            source_evidence_refs=["ci://run/A/result", "ci://run/B/result"],
            observed_symptom="fixture observation",
            request=request,
            identity_context={"triangulation_state": "CONVERGENCE"},
        )
        first = build_reflection_core(**kwargs)
        second = build_reflection_core(**kwargs)
        self.assertEqual(first.reflection_id, second.reflection_id)
        self.assertEqual("NONE", first.authority_effect)
        self.assertEqual("CANDIDATE_ONLY", first.promotion_state)

    def test_reflection_requires_competing_explanation_and_grounded_evidence(self):
        request = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
        request["alternative_explanations"] = []
        with self.assertRaisesRegex(ValueError, "alternative_explanations"):
            build_reflection_core(
                source_kind="EVIDENCE_DELTA",
                source_id="delta-example",
                source_digest="sha256:" + "b" * 64,
                source_evidence_refs=["ci://run/A/result"],
                observed_symptom="fixture observation",
                request=request,
            )

        request = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
        request["evidence_for"] = ["memory://unsupported"]
        with self.assertRaisesRegex(ValueError, "source_evidence_refs"):
            build_reflection_core(
                source_kind="EVIDENCE_DELTA",
                source_id="delta-example",
                source_digest="sha256:" + "c" * 64,
                source_evidence_refs=["ci://run/A/result"],
                observed_symptom="fixture observation",
                request=request,
            )


class ReflectionStoreTests(unittest.TestCase):
    def _prepare(self, db: Path):
        build(HOST_FIXTURE / "Devos", HOST_FIXTURE, db)
        episode = json.loads(EVIDENCE_FIXTURE.read_text(encoding="utf-8"))
        request = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
        connection = connect_runtime(db)
        evidence = persist_episode(connection, episode)
        delta_id = evidence["delta"]["delta_id"]
        return connection, delta_id, request

    def test_schema_v4_and_reflection_admission(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection, delta_id, request = self._prepare(db)
            try:
                result = persist_reflection(connection, delta_id, request)
                reflection = result["reflection"]
                self.assertFalse(result["replayed"])
                self.assertEqual("feature-lantern", reflection["branch_key"])
                self.assertEqual("NONE", reflection["authority_effect"])
                self.assertEqual("CANDIDATE_ONLY", reflection["promotion_state"])
                self.assertEqual(4, CURRENT_SCHEMA_VERSION)
                self.assertEqual(4, connection.execute("PRAGMA user_version").fetchone()[0])
            finally:
                connection.close()

    def test_identical_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection, delta_id, request = self._prepare(db)
            try:
                first = persist_reflection(connection, delta_id, request)
                second = persist_reflection(connection, delta_id, request)
                self.assertEqual(first["reflection"]["reflection_id"], second["reflection"]["reflection_id"])
                self.assertTrue(second["replayed"])
                self.assertEqual(1, connection.execute("SELECT count(*) FROM reflection_candidates").fetchone()[0])
            finally:
                connection.close()

    def test_competing_hypothesis_gets_distinct_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection, delta_id, request = self._prepare(db)
            try:
                first = persist_reflection(connection, delta_id, request)
                alternate = dict(request)
                alternate["mechanism_hypothesis"] = "the fixtures share an implementation path that masks input-sensitive state"
                alternate["alternative_explanations"] = ["the lantern transition is truly input-independent"]
                second = persist_reflection(connection, delta_id, alternate)
                self.assertNotEqual(first["reflection"]["reflection_id"], second["reflection"]["reflection_id"])
                self.assertEqual(2, len(list_reflections(connection, "feature-lantern")))
            finally:
                connection.close()

    def test_unknown_branch_is_rejected_at_admission(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection, delta_id, request = self._prepare(db)
            try:
                request["branch_key"] = "missing-branch"
                with self.assertRaisesRegex(ValueError, "unknown branch_key"):
                    persist_reflection(connection, delta_id, request)
            finally:
                connection.close()

    def test_projection_rebuild_preserves_reflections(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection, delta_id, request = self._prepare(db)
            try:
                persist_reflection(connection, delta_id, request)
            finally:
                connection.close()

            build(HOST_FIXTURE / "Devos", HOST_FIXTURE, db)
            connection = connect_runtime(db)
            try:
                self.assertEqual(1, connection.execute("SELECT count(*) FROM reflection_candidates").fetchone()[0])
                self.assertEqual("NONE", connection.execute("SELECT authority_effect FROM reflection_candidates").fetchone()[0])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
