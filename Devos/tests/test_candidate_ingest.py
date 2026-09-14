from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from build_knowledge_db import build, health, query
from candidate_ingest import ingest_pack
from db_runtime import connect_runtime

FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"
PACK = ROOT / "knowledge" / "reddit-harvest-03.json"
AGI_MEMORY_PACK = ROOT / "knowledge" / "agi-memory-delivery-fitness-01.json"
AGI_MEMORY_RESEARCH = "Devos/research/AGI_MEMORY_DELIVERY_FITNESS_01.md"


class CandidateIngestTests(unittest.TestCase):
    def make_context(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "candidate-ingest.db"
        build(FIXTURE / "Devos", FIXTURE, db, fresh=True)
        return db, connect_runtime(db)

    def test_reddit_harvest_pack_ingests_four_candidate_memories(self):
        _, connection = self.make_context()
        try:
            result = ingest_pack(connection, json.loads(PACK.read_text(encoding="utf-8")))
            self.assertEqual("STONE-20260914-DEVOS-REDDIT-HARVEST-03", result["pack_id"])
            self.assertEqual("project-core", result["branch_key"])
            self.assertEqual(4, len(result["entries"]))
            self.assertEqual("NONE", result["authority_effect"])
            self.assertEqual("CANDIDATE_ONLY", result["promotion_state"])
            self.assertTrue(all(row["maturity_stage"] == "RECOGNITION" for row in result["entries"]))
            self.assertTrue(all(not row["validated_for_transfer"] for row in result["entries"]))
            self.assertTrue(all(row["authority_effect"] == "NONE" for row in result["entries"]))
            self.assertTrue(all(row["promotion_state"] == "CANDIDATE_ONLY" for row in result["entries"]))
            self.assertEqual(8, connection.execute("SELECT count(*) FROM evidence_roots").fetchone()[0])
            self.assertEqual(8, connection.execute("SELECT count(*) FROM atomic_findings").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM evidence_delta_packets").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM reflection_candidates").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM learning_experiences").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM learning_procedures").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM learning_capabilities").fetchone()[0])
            memory_types = {
                json.loads(row[0])["memory_type"]
                for row in connection.execute(
                    "SELECT payload_json FROM learning_experiences ORDER BY memory_id"
                ).fetchall()
            }
            self.assertEqual({"SEMANTIC", "PROCEDURAL", "NEGATIVE"}, memory_types)
        finally:
            connection.close()

    def test_pack_replay_is_idempotent(self):
        _, connection = self.make_context()
        try:
            pack = json.loads(PACK.read_text(encoding="utf-8"))
            first = ingest_pack(connection, pack)
            second = ingest_pack(connection, pack)
            self.assertTrue(all(not row["learning_replayed"] for row in first["entries"]))
            self.assertTrue(all(row["reflection_replayed"] for row in second["entries"]))
            self.assertTrue(all(row["learning_replayed"] for row in second["entries"]))
            self.assertEqual(4, connection.execute("SELECT count(*) FROM learning_capability_events").fetchone()[0])
            self.assertEqual(4, connection.execute("SELECT count(*) FROM learning_experiences").fetchone()[0])
        finally:
            connection.close()

    def test_pack_cannot_override_lineage_or_scope(self):
        _, connection = self.make_context()
        try:
            pack = json.loads(PACK.read_text(encoding="utf-8"))
            pack["entries"][0]["procedure"]["source_evidence_refs"] = ["invented://support"]
            with self.assertRaisesRegex(ValueError, "lineage-controlled fields"):
                ingest_pack(connection, pack)

            pack = json.loads(PACK.read_text(encoding="utf-8"))
            pack["branch_key"] = "missing-branch"
            with self.assertRaisesRegex(ValueError, "unknown branch_key"):
                ingest_pack(connection, pack)
        finally:
            connection.close()

    def test_agi_memory_pack_materializes_from_repository_projection_and_queries_back(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "merged-main-materialization.db"
        host_root = ROOT.parent

        built = build(ROOT, host_root, db, fresh=True)
        self.assertTrue(built["ok"])

        projected = query(db, "delivered", limit=20)
        self.assertTrue(
            any(row["path"] == AGI_MEMORY_RESEARCH for row in projected),
            "merged research packet must be retrievable from the repository projection",
        )

        connection = connect_runtime(db)
        try:
            result = ingest_pack(
                connection,
                json.loads(AGI_MEMORY_PACK.read_text(encoding="utf-8")),
            )
            self.assertEqual("STONE-20260914-DEVOS-AGI-MEMORY-DELIVERY-01", result["pack_id"])
            self.assertEqual("project-core", result["branch_key"])
            self.assertEqual(2, len(result["entries"]))
            self.assertEqual("NONE", result["authority_effect"])
            self.assertEqual("CANDIDATE_ONLY", result["promotion_state"])
            self.assertTrue(all(row["maturity_stage"] == "RECOGNITION" for row in result["entries"]))
            self.assertTrue(all(not row["validated_for_transfer"] for row in result["entries"]))

            capability_keys = {
                json.loads(row[0])["capability_key"]
                for row in connection.execute(
                    "SELECT payload_json FROM learning_capabilities ORDER BY capability_id"
                ).fetchall()
            }
            self.assertEqual(
                {"devos.context.delivery_fitness", "devos.metadata.structural_capture"},
                capability_keys,
            )
            counts = {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in (
                    "evidence_roots",
                    "atomic_findings",
                    "evidence_delta_packets",
                    "reflection_candidates",
                    "learning_experiences",
                    "learning_procedures",
                    "learning_capabilities",
                    "learning_capability_events",
                )
            }
        finally:
            connection.close()

        receipt = {
            "pack_id": result["pack_id"],
            "branch_key": result["branch_key"],
            "authority_effect": result["authority_effect"],
            "promotion_state": result["promotion_state"],
            "maturity_stages": [row["maturity_stage"] for row in result["entries"]],
            "validated_for_transfer": [row["validated_for_transfer"] for row in result["entries"]],
            "capability_keys": sorted(capability_keys),
            "runtime_counts": counts,
            "query_paths": sorted({row["path"] for row in projected}),
            "health": health(db),
        }
        print("DEVOS_RUNTIME_EVIDENCE=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
