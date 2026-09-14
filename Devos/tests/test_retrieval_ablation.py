from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from build_knowledge_db import build
from db_runtime import connect_runtime
from knowledge_runtime import build_packet
from retrieval_ablation import (
    ARMS,
    BENCHMARK_ID,
    FTS5_BM25_V1,
    FTS5_WEIGHTS,
    LEXICAL_V1,
    compile_fts5_query,
    retrieve,
    run_benchmark,
)

FIXTURE = ROOT / "tests" / "fixtures" / "retrieval_ablation"
HOST = FIXTURE / "host"
BENCHMARK = FIXTURE / "benchmark.json"
CANDIDATE = "0" * 40


class RetrievalAblationTests(unittest.TestCase):
    def make_runtime(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "retrieval.db"
        build(HOST / "Devos", HOST, db, fresh=True)
        connection = connect_runtime(db)
        self.addCleanup(connection.close)
        return db, connection

    def load_spec(self):
        return json.loads(BENCHMARK.read_text(encoding="utf-8"))

    def test_lexical_v1_matches_production_document_order(self):
        _, connection = self.make_runtime()
        query = "priority beacon"
        branches = ["feature-alpha"]
        packet = build_packet(
            connection,
            HOST,
            query,
            branches,
            limit_documents=6,
            limit_tasks=0,
            limit_tools=0,
            max_document_chars=6000,
        )
        baseline = retrieve(connection, query, branches, LEXICAL_V1, limit=6)
        packet_ids = [
            (row["path"], row["section"])
            for row in packet["context"]["documents"]
        ]
        baseline_ids = [(row["path"], row["section"]) for row in baseline]
        self.assertEqual(packet_ids, baseline_ids)

    def test_safe_fts5_compiler_quotes_operator_words_and_hyphenated_identifiers(self):
        compiled = compile_fts5_query("alpha OR retry_guard-v2")
        self.assertEqual('"alpha" OR "or" OR "retry_guard-v2"', compiled)
        self.assertNotEqual("alpha OR retry_guard-v2", compiled)

    def test_fts5_arm_excludes_sibling_scope_and_preserves_direct_tier(self):
        _, connection = self.make_runtime()
        rows = retrieve(connection, "beacon", ["feature-alpha"], FTS5_BM25_V1, limit=10)
        self.assertTrue(rows)
        self.assertTrue(all(not row["path"].startswith("docs/beta/") for row in rows))
        self.assertEqual(0, rows[0]["branch_tier"])
        tiers = [row["branch_tier"] for row in rows]
        self.assertEqual(tiers, sorted(tiers))

    def test_scope_local_fts5_statistics_ignore_sibling_injection(self):
        _, connection = self.make_runtime()
        before = retrieve(
            connection, "vector lantern", ["feature-alpha"], FTS5_BM25_V1, limit=10
        )
        for idx in range(50):
            connection.execute(
                "INSERT INTO documents(path,title,section,content,content_hash,kind) "
                "VALUES (?,?,?,?,?,?)",
                (
                    f"docs/beta/generated-{idx}.md",
                    "Sibling Decoy",
                    "Sibling Decoy",
                    "vector lantern " * 20,
                    f"sibling-{idx:04d}",
                    "documentation",
                ),
            )
        connection.commit()
        after = retrieve(
            connection, "vector lantern", ["feature-alpha"], FTS5_BM25_V1, limit=10
        )
        before_signature = [
            (row["path"], row["section"], row["score"]) for row in before
        ]
        after_signature = [
            (row["path"], row["section"], row["score"]) for row in after
        ]
        self.assertEqual(before_signature, after_signature)

    def test_frozen_benchmark_is_two_arm_only_and_receipt_is_deterministic(self):
        _, connection = self.make_runtime()
        spec = self.load_spec()
        first = run_benchmark(connection, spec, candidate_revision=CANDIDATE)
        second = run_benchmark(connection, spec, candidate_revision=CANDIDATE)
        self.assertEqual(BENCHMARK_ID, first["benchmark_id"])
        self.assertEqual(set(ARMS), set(first["arms"]))
        self.assertEqual(
            {"path": 3.0, "title": 6.0, "section": 4.0, "content": 1.0},
            first["arms"][FTS5_BM25_V1]["weights"],
        )
        self.assertEqual(dict(FTS5_WEIGHTS), first["arms"][FTS5_BM25_V1]["weights"])
        self.assertEqual("BENCHMARK_ONLY", first["promotion_state"])
        self.assertEqual("NONE", first["authority_effect"])
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertFalse(first["third_arm_gate"]["eligible_for_research"])
        for arm in ARMS:
            aggregate = first["evaluations"][arm]["aggregate"]
            self.assertEqual(0, aggregate["scope_leakage_count"])
            self.assertEqual(0, aggregate["branch_tier_violation_count"])
            self.assertEqual(1.0, aggregate["recall_at_5"])
            self.assertEqual(1.0, aggregate["expected_empty_accuracy"])

    def test_third_arm_gate_opens_only_on_shared_specific_recall_failure(self):
        _, connection = self.make_runtime()
        spec = self.load_spec()
        spec["queries"] = [
            {
                "query_id": "shared-failure",
                "split": "holdout",
                "query": "lantern_mode",
                "branches": ["feature-alpha"],
                "relevant": ["docs/alpha/missing.md#Missing"],
            }
        ]
        result = run_benchmark(connection, spec, candidate_revision=CANDIDATE)
        self.assertTrue(result["third_arm_gate"]["eligible_for_research"])
        self.assertEqual(
            ["shared-failure"],
            result["third_arm_gate"]["specific_shared_recall_failures"],
        )

    def test_unknown_third_arm_is_rejected(self):
        _, connection = self.make_runtime()
        with self.assertRaisesRegex(ValueError, "unsupported retrieval arm"):
            retrieve(connection, "lantern", ["feature-alpha"], "VECTOR_V1")

    def test_spec_cannot_supply_extra_arms(self):
        _, connection = self.make_runtime()
        spec = self.load_spec()
        spec["arms"] = ["LEXICAL_V1", "FTS5_BM25_V1", "VECTOR_V1"]
        with self.assertRaisesRegex(ValueError, "arms are fixed"):
            run_benchmark(connection, spec, candidate_revision=CANDIDATE)

    def test_receipt_requires_exact_git_revision_identity(self):
        _, connection = self.make_runtime()
        with self.assertRaisesRegex(ValueError, "40-character lowercase Git SHA"):
            run_benchmark(connection, self.load_spec(), candidate_revision="main")


if __name__ == "__main__":
    unittest.main()
