from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from db_runtime import BUSY_TIMEOUT_MS, CURRENT_SCHEMA_VERSION, connect_runtime, runtime_health
from build_knowledge_db import build, query

FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"


class KnowledgeDbTests(unittest.TestCase):
    def test_runtime_policy_and_schema_are_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "runtime.db"
            connection = connect_runtime(db)
            try:
                health = runtime_health(connection)
                self.assertEqual(CURRENT_SCHEMA_VERSION, health["schema_version"])
                self.assertEqual(CURRENT_SCHEMA_VERSION, health["user_version"])
                self.assertEqual("wal", health["journal_mode"])
                self.assertTrue(health["foreign_keys"])
                self.assertEqual(BUSY_TIMEOUT_MS, health["busy_timeout_ms"])
                self.assertEqual("ok", health["integrity_check"])
            finally:
                connection.close()

            connection = connect_runtime(db)
            try:
                self.assertEqual(
                    1,
                    connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0],
                )
            finally:
                connection.close()

    def test_build_materializes_repo_knowledge_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "knowledge.db"
            result = build(FIXTURE / "Devos", FIXTURE, db)
            self.assertEqual(2, result["branches"])
            self.assertEqual(2, result["tasks"])
            self.assertEqual(1, result["tools"])
            self.assertTrue(query(db, "lantern"))

            connection = connect_runtime(db)
            try:
                task = connection.execute(
                    "SELECT status, assigned_agent FROM devos_tasks WHERE task_id='DEV-001'"
                ).fetchone()
                self.assertEqual("DONE", task["status"])
                self.assertEqual("fixture-agent", task["assigned_agent"])
                edge = connection.execute(
                    "SELECT 1 FROM task_dependencies WHERE task_id='DEV-002' AND depends_on_task_id='DEV-001'"
                ).fetchone()
                self.assertIsNotNone(edge)
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT 1 FROM build_manifest WHERE source_path='README.md'"
                    ).fetchone()
                )
            finally:
                connection.close()

    def test_rebuild_is_logically_deterministic_and_preserves_runtime_state(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "knowledge.db"
            first = build(FIXTURE / "Devos", FIXTURE, db)
            connection = connect_runtime(db)
            try:
                connection.execute(
                    "INSERT INTO runtime_kv VALUES ('note', ?, ?)",
                    (json.dumps({"kept": True}), "t1"),
                )
                connection.commit()
            finally:
                connection.close()

            second = build(FIXTURE / "Devos", FIXTURE, db)
            self.assertEqual(first["projection_digest"], second["projection_digest"])
            connection = connect_runtime(db)
            try:
                self.assertEqual(
                    1,
                    connection.execute("SELECT count(*) FROM runtime_kv WHERE key='note'").fetchone()[0],
                )
            finally:
                connection.close()

    def test_fresh_rebuild_removes_runtime_state(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "knowledge.db"
            build(FIXTURE / "Devos", FIXTURE, db)
            connection = connect_runtime(db)
            try:
                connection.execute("INSERT INTO runtime_kv VALUES ('note', '{}', 't1')")
                connection.commit()
            finally:
                connection.close()

            build(FIXTURE / "Devos", FIXTURE, db, fresh=True)
            connection = connect_runtime(db)
            try:
                self.assertEqual(0, connection.execute("SELECT count(*) FROM runtime_kv").fetchone()[0])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
