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
from evidence_runtime import (
    AtomicFinding,
    CrossReference,
    CurrentClaim,
    LineageState,
    TriangulationState,
    build_delta_packet,
    cross_reference,
    summarize_roots,
    triangulate,
)
from evidence_store import persist_episode

FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"
EPISODE = ROOT / "tests" / "fixtures" / "evidence" / "episode-convergence.json"


class EvidenceRuntimeTests(unittest.TestCase):
    def test_derivative_artifacts_do_not_multiply_independent_roots(self):
        findings = [
            AtomicFinding("root", "claim", "value", "run://1", ("root-1",), LineageState.INDEPENDENT_ROOT),
            AtomicFinding("log", "claim", "value", "run://1/log", ("root-1",), LineageState.DERIVED),
            AtomicFinding("summary", "claim", "value", "doc://summary", ("root-1",), LineageState.QUOTATION_OR_SUMMARY),
        ]
        summary = summarize_roots(findings)
        self.assertEqual(3, summary.artifact_count)
        self.assertEqual(("root-1",), summary.independent_root_ids)

    def test_independent_replication_converges(self):
        current = {"claim": CurrentClaim("claim-id", "claim", "stable")}
        findings = [
            AtomicFinding("a", "claim", "stable", "run://a", ("a-root",), LineageState.INDEPENDENT_ROOT),
            AtomicFinding("b", "claim", "stable", "run://b", ("b-root",), LineageState.REPLICATION_NEW_INPUTS),
        ]
        assessments = [cross_reference(finding, current) for finding in findings]
        result = triangulate(assessments, claim_key="claim")
        self.assertEqual(TriangulationState.CONVERGENCE, result.state)
        self.assertEqual(2, result.root_summary.independent_root_count)

    def test_divergence_is_explicit_and_authority_neutral(self):
        current = {"claim": CurrentClaim("claim-id", "claim", "passes")}
        findings = [
            AtomicFinding("a", "claim", "passes", "run://a", ("a-root",), LineageState.INDEPENDENT_ROOT),
            AtomicFinding("b", "claim", "fails", "run://b", ("b-root",), LineageState.REPLICATION_NEW_INPUTS),
        ]
        assessments = [cross_reference(finding, current) for finding in findings]
        tri = triangulate(assessments, claim_key="claim")
        packet = build_delta_packet(assessments, tri, current)
        self.assertEqual(TriangulationState.DIVERGENCE, tri.state)
        self.assertEqual("REVIEW_CONFLICT", packet.recommended_action)
        self.assertEqual("NONE", packet.authority_effect)

    def test_supersession_is_review_only(self):
        current = {"claim": CurrentClaim("old", "claim", "old value")}
        finding = AtomicFinding(
            "new", "claim", "new value", "pr://1", ("root",),
            LineageState.INDEPENDENT_ROOT, supersedes_claim_id="old"
        )
        assessment = cross_reference(finding, current)
        self.assertEqual(CrossReference.SUPERSEDES, assessment.cross_reference)
        tri = triangulate([assessment], claim_key="claim")
        packet = build_delta_packet([assessment], tri, current)
        self.assertEqual("REVIEW_SUPERSESSION", packet.recommended_action)
        self.assertEqual("NONE", packet.authority_effect)


class EvidenceStoreTests(unittest.TestCase):
    def make_db(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "knowledge.db"
        build(FIXTURE / "Devos", FIXTURE, db, fresh=True)
        return db

    def load_episode(self):
        return json.loads(EPISODE.read_text(encoding="utf-8"))

    def test_current_schema_and_episode_admission(self):
        db = self.make_db()
        connection = connect_runtime(db)
        try:
            self.assertEqual(6, CURRENT_SCHEMA_VERSION)
            result = persist_episode(connection, self.load_episode())
            self.assertEqual("CONVERGENCE", result["triangulation_state"])
            self.assertEqual("NONE", result["authority_effect"])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM evidence_roots").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM atomic_findings").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM evidence_delta_packets").fetchone()[0])
        finally:
            connection.close()

    def test_identical_replay_is_idempotent(self):
        db = self.make_db()
        episode = self.load_episode()
        connection = connect_runtime(db)
        try:
            first = persist_episode(connection, episode)
            second = persist_episode(connection, episode)
            self.assertEqual(first["batch_id"], second["batch_id"])
            self.assertEqual(first["delta"]["delta_id"], second["delta"]["delta_id"])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM atomic_findings").fetchone()[0])
        finally:
            connection.close()

    def test_conflicting_reuse_of_finding_id_is_rejected(self):
        db = self.make_db()
        episode = self.load_episode()
        connection = connect_runtime(db)
        try:
            persist_episode(connection, episode)
            mutated = self.load_episode()
            mutated["findings"][0]["value"] = "mutated historical value"
            with self.assertRaisesRegex(ValueError, "immutable evidence conflict"):
                persist_episode(connection, mutated)
        finally:
            connection.close()

    def test_normal_projection_rebuild_preserves_evidence(self):
        db = self.make_db()
        connection = connect_runtime(db)
        try:
            persist_episode(connection, self.load_episode())
        finally:
            connection.close()
        build(FIXTURE / "Devos", FIXTURE, db)
        connection = connect_runtime(db)
        try:
            self.assertEqual(2, connection.execute("SELECT count(*) FROM atomic_findings").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM evidence_delta_packets").fetchone()[0])
        finally:
            connection.close()

    def test_unknown_branch_and_root_are_rejected(self):
        db = self.make_db()
        connection = connect_runtime(db)
        try:
            bad_branch = self.load_episode()
            bad_branch["branch_key"] = "missing-branch"
            with self.assertRaisesRegex(ValueError, "unknown branch_key"):
                persist_episode(connection, bad_branch)
            bad_root = self.load_episode()
            bad_root["findings"][0]["root_ids"] = ["missing-root"]
            with self.assertRaisesRegex(ValueError, "unknown root ids"):
                persist_episode(connection, bad_root)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
