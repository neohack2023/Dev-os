from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from build_knowledge_db import build
from db_runtime import connect_runtime
from knowledge_runtime import build_packet, projection_freshness, status_payload

FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"


class KnowledgeRuntimeTests(unittest.TestCase):
    def make_runtime(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        host = Path(tempdir.name) / "host"
        shutil.copytree(FIXTURE, host)
        db = Path(tempdir.name) / "knowledge.db"
        build(host / "Devos", host, db)
        connection = connect_runtime(db)
        self.addCleanup(connection.close)
        return host, db, connection

    def test_packet_resolves_branch_closure_and_ranks_direct_scope_first(self):
        host, _, connection = self.make_runtime()
        packet = build_packet(connection, host, "lantern", ["feature-lantern"])
        self.assertEqual(["project-core", "feature-lantern"], packet["resolved_branches"])
        self.assertTrue(packet["context"]["documents"])
        self.assertEqual("docs/architecture.md", packet["context"]["documents"][0]["path"])
        self.assertEqual(0, packet["context"]["documents"][0]["branch_tier"])
        self.assertTrue(packet["context"]["tasks"])
        self.assertEqual("DEV-002", packet["context"]["tasks"][0]["task_id"])
        self.assertEqual("BLOCKED", packet["context"]["tasks"][0]["status"])

    def test_packet_hash_is_deterministic_and_provenance_is_bound(self):
        host, _, connection = self.make_runtime()
        first = build_packet(connection, host, "lantern", ["feature-lantern"])
        second = build_packet(connection, host, "lantern", ["feature-lantern"])
        self.assertEqual(first["packet_hash"], second["packet_hash"])
        paths = {row["path"] for row in first["source_manifest"]}
        self.assertIn("Devos/branches.jsonl", paths)
        self.assertIn("Devos/tasks.jsonl", paths)
        self.assertIn("docs/architecture.md", paths)
        self.assertEqual(first["projection"]["digest"], status_payload(connection, host)["projection_digest"])

    def test_tool_selection_is_query_scored(self):
        host, _, connection = self.make_runtime()
        packet = build_packet(connection, host, "fixture", ["project-core"])
        self.assertTrue(packet["context"]["tools"])
        self.assertEqual("fixture-tool", packet["context"]["tools"][0]["tool_key"])
        self.assertNotIn("payload_json", packet["context"]["tools"][0])

    def test_document_budget_is_hard_bounded(self):
        host, _, connection = self.make_runtime()
        packet = build_packet(
            connection,
            host,
            "lantern",
            ["feature-lantern"],
            max_document_chars=12,
        )
        self.assertLessEqual(packet["document_chars_used"], 12)
        self.assertTrue(all(len(row["excerpt"]) <= 12 for row in packet["context"]["documents"]))

    def test_unknown_branch_is_rejected(self):
        host, _, connection = self.make_runtime()
        with self.assertRaisesRegex(ValueError, "unknown branch_key"):
            build_packet(connection, host, "lantern", ["missing-branch"])

    def test_stale_projection_is_visible_without_implicit_refresh(self):
        host, _, connection = self.make_runtime()
        before = projection_freshness(connection, host)
        self.assertTrue(before["fresh"])
        path = host / "docs" / "architecture.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged after projection\n", encoding="utf-8")
        after = projection_freshness(connection, host)
        self.assertFalse(after["fresh"])
        self.assertIn("docs/architecture.md", after["changed_sources"])

    def test_packet_is_json_serializable(self):
        host, _, connection = self.make_runtime()
        packet = build_packet(connection, host, "lantern", ["feature-lantern"])
        encoded = json.dumps(packet, sort_keys=True)
        self.assertIn(packet["packet_hash"], encoded)


if __name__ == "__main__":
    unittest.main()
