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
from reflection_store import persist_reflection
from learning_store import admit_bundle
from promotion_gate import persist_envelope, persist_decision

HOST = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"
EPISODE = ROOT / "tests" / "fixtures" / "evidence" / "episode-convergence.json"
REFLECTION = ROOT / "tests" / "fixtures" / "reflection" / "request-lantern.json"
REVISION = "a" * 40


class PromotionGateTests(unittest.TestCase):
    def _context(self, *, regression_safe: bool = True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "promotion.db"
        build(HOST / "Devos", HOST, db, fresh=True)
        connection = connect_runtime(db)
        episode = json.loads(EPISODE.read_text(encoding="utf-8"))
        evidence = persist_episode(connection, episode)
        reflection_request = json.loads(REFLECTION.read_text(encoding="utf-8"))
        reflection = persist_reflection(
            connection, evidence["delta"]["delta_id"], reflection_request
        )["reflection"]
        refs = list(reflection["source_evidence_refs"])
        learning = {
            "observed_at": "2026-09-13T23:12:00+00:00",
            "procedure": {
                "branch_scope": "feature-lantern",
                "name": "lantern-stability-check",
                "version": "1",
                "trigger_conditions": ["lantern state available"],
                "input_schema": ["state"],
                "output_schema": ["stable"],
                "implementation_ref": "tests:lantern_stability_check",
                "source_reflection_ids": [reflection["reflection_id"]],
                "source_evidence_refs": refs,
                "known_failures": ["hidden mutable ordering"],
            },
            "evaluation": {"results": [
                {"fixture_id": "inv", "tier": "T0", "passed": True, "input_identity": "contract"},
                {"fixture_id": "known", "tier": "T1", "passed": True, "input_identity": "fixture-A"},
                {"fixture_id": "dev", "tier": "T2", "passed": True, "input_identity": "fixture-B"},
                {"fixture_id": "holdout", "tier": "T3", "passed": True, "input_identity": "fixture-C"},
                {"fixture_id": "regression", "tier": "T4", "passed": regression_safe, "input_identity": "fixture-R"},
                {"fixture_id": "canary", "tier": "T5", "passed": True, "input_identity": "real-canary"},
            ]},
            "capability": {
                "capability_key": "lantern.stability",
                "description": "Recognize deterministic lantern state across unseen inputs.",
                "known_tasks": ["lantern stability"],
                "known_failure_modes": ["hidden mutable ordering"],
            },
            "experience": {
                "memory_type": "PROCEDURAL",
                "statement": "Lantern stability transferred to held-out inputs.",
            },
        }
        learned = admit_bundle(connection, learning)
        return db, connection, learned["capability_id"]

    def _request(self, capability_id: str, *, review: bool = True, canary: bool = True):
        return {
            "observed_at": "2026-09-13T23:30:00+00:00",
            "capability_id": capability_id,
            "candidate_revision": REVISION,
            "change_digest": "b" * 64,
            "target": {
                "repository": "owner/fixture",
                "branch": "main",
                "paths": ["Devos/runtime/example.py", "Devos/tests/test_example.py"],
                "change_ref": f"git:{REVISION}",
            },
            "expected_benefit": "Apply the transferred lantern stability procedure.",
            "regression_risk": "Could alter unrelated state normalization.",
            "falsification_test": "Run held-out and regression fixtures against the candidate revision.",
            "rollback_plan": "Restore the previous known-good revision and rerun required checks.",
            "verification_plan": {
                "required_checks": [{"name": "unit-suite", "source": "github-actions"}],
                "require_independent_review": review,
                "review_source": "github-review" if review else "",
                "require_canary": canary,
                "canary_source": "github-environment" if canary else "",
            },
            "required_authorization": "reviewed repository change",
            "destination_authority": "repository",
        }

    def _verification(self, *, review: bool = True, canary: bool = True):
        payload = {
            "observed_at": "2026-09-13T23:31:00+00:00",
            "candidate_revision": REVISION,
            "checks": [{
                "name": "unit-suite", "source": "github-actions", "status": "success", "revision": REVISION
            }],
            "rollback": {"ready": True, "triggered": False, "verified": False},
        }
        if review:
            payload["review"] = {
                "source": "github-review", "status": "approved", "revision": REVISION, "self_review": False
            }
        if canary:
            payload["canary"] = {
                "source": "github-environment", "status": "success", "revision": REVISION
            }
        return payload

    def test_schema_v5_and_locked_stone_envelope(self):
        db, connection, capability_id = self._context()
        try:
            self.assertEqual(5, CURRENT_SCHEMA_VERSION)
            result = persist_envelope(connection, self._request(capability_id))
            envelope = result["envelope"]
            self.assertEqual("LOCKED", envelope["stone_state"])
            self.assertEqual("HANDOFF_REQUIRED", envelope["mason_state"])
            self.assertEqual("TRANSFER", envelope["source_learning"]["maturity_stage"])
            self.assertTrue(envelope["source_learning"]["evidence_refs"])
            self.assertEqual("NONE", envelope["authority_effect"])
            self.assertFalse(envelope["write_authorized"])
        finally:
            connection.close()

    def test_promotion_requires_regression_safe_learning(self):
        db, connection, capability_id = self._context(regression_safe=False)
        try:
            with self.assertRaisesRegex(ValueError, "regression-safe"):
                persist_envelope(connection, self._request(capability_id))
        finally:
            connection.close()

    def test_verifier_revision_mismatch_is_rejected(self):
        db, connection, capability_id = self._context()
        try:
            envelope = persist_envelope(connection, self._request(capability_id))["envelope"]
            verification = self._verification()
            verification["checks"][0]["revision"] = "c" * 40
            with self.assertRaisesRegex(ValueError, "status check is not bound"):
                persist_decision(connection, envelope["envelope_id"], verification)
        finally:
            connection.close()

    def test_missing_required_gates_produces_revise(self):
        db, connection, capability_id = self._context()
        try:
            envelope = persist_envelope(connection, self._request(capability_id))["envelope"]
            verification = self._verification(review=False, canary=False)
            decision = persist_decision(connection, envelope["envelope_id"], verification)["decision"]
            self.assertEqual("REVISE", decision["outcome"])
            self.assertTrue(any("review" in reason for reason in decision["reasons"]))
            self.assertTrue(any("canary" in reason for reason in decision["reasons"]))
        finally:
            connection.close()

    def test_full_verification_promotes_without_write_authority(self):
        db, connection, capability_id = self._context()
        try:
            envelope = persist_envelope(connection, self._request(capability_id))["envelope"]
            result = persist_decision(connection, envelope["envelope_id"], self._verification())
            decision = result["decision"]
            self.assertEqual("PROMOTE", decision["outcome"])
            self.assertEqual("MASON_REVIEW_PROMOTION", decision["next_action"])
            self.assertTrue(decision["mason_handoff_required"])
            self.assertFalse(decision["write_authorized"])
            self.assertEqual("NONE", decision["authority_effect"])
        finally:
            connection.close()

    def test_verified_rollback_is_explicit(self):
        db, connection, capability_id = self._context()
        try:
            envelope = persist_envelope(connection, self._request(capability_id))["envelope"]
            verification = self._verification()
            verification["rollback"] = {"ready": True, "triggered": True, "verified": True}
            decision = persist_decision(connection, envelope["envelope_id"], verification)["decision"]
            self.assertEqual("ROLLBACK", decision["outcome"])
            self.assertEqual("MASON_REVIEW_ROLLBACK", decision["next_action"])
        finally:
            connection.close()

    def test_exact_replay_is_idempotent(self):
        db, connection, capability_id = self._context()
        try:
            request = self._request(capability_id)
            first_envelope = persist_envelope(connection, request)
            second_envelope = persist_envelope(connection, request)
            self.assertFalse(first_envelope["replayed"])
            self.assertTrue(second_envelope["replayed"])
            verification = self._verification()
            first = persist_decision(connection, first_envelope["envelope"]["envelope_id"], verification)
            second = persist_decision(connection, first_envelope["envelope"]["envelope_id"], verification)
            self.assertFalse(first["replayed"])
            self.assertTrue(second["replayed"])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM promotion_decisions").fetchone()[0])
        finally:
            connection.close()

    def test_projection_rebuild_preserves_promotion_receipts(self):
        db, connection, capability_id = self._context()
        envelope = persist_envelope(connection, self._request(capability_id))["envelope"]
        persist_decision(connection, envelope["envelope_id"], self._verification())
        connection.close()
        build(HOST / "Devos", HOST, db)
        connection = connect_runtime(db)
        try:
            self.assertEqual(1, connection.execute("SELECT count(*) FROM promotion_envelopes").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM promotion_decisions").fetchone()[0])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
