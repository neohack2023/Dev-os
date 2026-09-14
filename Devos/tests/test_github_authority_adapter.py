from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from db_runtime import CURRENT_SCHEMA_VERSION, connect_runtime
from github_authority_adapter import prepare_remote, open_pr, verify_ready, merge_remote

BASE = "a" * 40
CANDIDATE = "b" * 40
MERGE = "c" * 40


class FakeGitHub:
    def __init__(self):
        self.branches = {
            "main": {"protected": True, "commit": {"sha": BASE}},
            "devos/candidate": {"protected": False, "commit": {"sha": CANDIDATE}},
        }
        self.rule_rows = [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
            {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci"}]}},
        ]
        self.protection_row = None
        self.pr_row = None
        self.review_rows = [{"state": "APPROVED", "user": {"login": "reviewer"}}]
        self.status_row = {"statuses": [{"context": "ci", "state": "success"}]}
        self.check_rows = []
        self.merge_response = {"merged": True, "sha": MERGE, "message": "merged"}
        self.commit_rows = {MERGE: {"parents": [{"sha": BASE}, {"sha": CANDIDATE}]}}

    def branch(self, repository, branch): return self.branches[branch]
    def rules(self, repository, branch): return list(self.rule_rows)
    def protection(self, repository, branch): return self.protection_row
    def open_prs(self, repository, head, base): return [] if self.pr_row is None else [self.pr_row]
    def create_pr(self, repository, head, base, title, body):
        self.pr_row = {"number": 7, "state": "open", "mergeable": True, "html_url": "https://example/pr/7", "head": {"sha": CANDIDATE}, "base": {"ref": "main"}}
        return self.pr_row
    def pr(self, repository, number): return self.pr_row
    def reviews(self, repository, number): return list(self.review_rows)
    def status(self, repository, revision): return self.status_row
    def check_runs(self, repository, revision): return list(self.check_rows)
    def merge_pr(self, repository, number, revision):
        if self.merge_response.get("merged"):
            self.branches["main"] = {"protected": True, "commit": {"sha": MERGE}}
            if self.pr_row: self.pr_row["state"] = "closed"
        return dict(self.merge_response)
    def commit(self, repository, revision): return self.commit_rows[revision]


class GitHubAuthorityAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "authority.db"
        self.connection = connect_runtime(self.db); self.addCleanup(self.connection.close)
        self.client = FakeGitHub()
        self._seed_mason()

    def _seed_mason(self, *, outcome="APPLIED"):
        capability_id="capability:fixture"; envelope_id="envelope:fixture"; decision_id="decision:fixture"
        self.connection.execute("INSERT INTO learning_capabilities(capability_id,payload_json) VALUES (?,?)",(capability_id,"{}"))
        envelope={"envelope_id":envelope_id,"candidate_revision":CANDIDATE,"change_digest":"d"*64,"stone_state":"LOCKED","mason_state":"HANDOFF_REQUIRED","target":{"repository":"owner/fixture","branch":"main","paths":["src/value.txt"]}}
        self.connection.execute("INSERT INTO promotion_envelopes(envelope_id,capability_id,branch_scope,candidate_revision,change_digest,stone_state,mason_state,payload_json,observed_at,authority_effect,write_authorized) VALUES (?,?,?,?,?,?,?,?,?,?,0)",(envelope_id,capability_id,"project-core",CANDIDATE,"d"*64,"LOCKED","HANDOFF_REQUIRED",json.dumps(envelope,sort_keys=True,separators=(",",":")),"2026-09-13T23:59:00Z","NONE"))
        decision={"decision_id":decision_id,"envelope_id":envelope_id,"candidate_revision":CANDIDATE,"outcome":"PROMOTE","next_action":"MASON_REVIEW_PROMOTION","write_authorized":False}
        self.connection.execute("INSERT INTO promotion_decisions(decision_id,envelope_id,outcome,candidate_revision,verifier_digest,payload_json,observed_at,authority_effect,write_authorized) VALUES (?,?,?,?,?,?,?,?,0)",(decision_id,envelope_id,"PROMOTE",CANDIDATE,"f"*64,json.dumps(decision,sort_keys=True,separators=(",",":")),"2026-09-13T23:59:30Z","NONE"))
        mason_plan={"plan_id":"mason-plan:fixture","decision_id":decision_id,"envelope_id":envelope_id,"repository":"owner/fixture","target_branch":"main","base_revision":BASE,"candidate_revision":CANDIDATE,"change_digest":"d"*64}
        self.connection.execute(
            "INSERT INTO mason_execution_plans(plan_id,decision_id,envelope_id,target_branch,base_revision,candidate_revision,change_digest,authorization_digest,payload_json,prepared_at,local_execution_authorized,remote_write_authorized) VALUES (?,?,?,?,?,?,?,?,?,?,1,0)",
            ("mason-plan:fixture",decision_id,envelope_id,"main",BASE,CANDIDATE,"d"*64,"e"*64,json.dumps(mason_plan,sort_keys=True,separators=(",",":")),"2026-09-14T00:00:00Z"),
        )
        receipt = {"receipt_id":"mason-receipt:fixture","plan_id":"mason-plan:fixture","outcome":outcome,"base_revision":BASE,"candidate_revision":CANDIDATE,"post_revision":CANDIDATE if outcome=="APPLIED" else BASE,"change_digest":"d"*64,"remote_authority_effect":"NONE","remote_write_performed":False}
        self.connection.execute(
            "INSERT INTO mason_execution_receipts(receipt_id,plan_id,outcome,base_revision,post_revision,change_digest,payload_json,observed_at,local_authority_effect,remote_authority_effect,remote_write_performed) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (receipt["receipt_id"],receipt["plan_id"],outcome,BASE,receipt["post_revision"],"d"*64,json.dumps(receipt,sort_keys=True,separators=(",",":")),"2026-09-14T00:01:00Z","LOCAL_GIT_REF_UPDATED" if outcome=="APPLIED" else "NONE","NONE"),
        )
        self.connection.commit()

    def request(self):
        return {"observed_at":"2026-09-14T00:02:00Z","candidate_branch":"devos/candidate","authorization":{"authorization_id":"auth:github","source":"fixture-operator","actor":"reviewer","observed_at":"2026-09-14T00:02:00Z","grant":"GITHUB_PR_MERGE","mason_receipt_id":"mason-receipt:fixture","candidate_revision":CANDIDATE,"repository":"owner/fixture","target_branch":"main","candidate_branch":"devos/candidate","approved":True}}

    def prepare(self): return prepare_remote(self.connection,"mason-receipt:fixture",self.client,self.request())["plan"]

    def test_schema_v7_and_prepare_binds_policy(self):
        plan = self.prepare(); self.assertEqual(7, CURRENT_SCHEMA_VERSION); self.assertTrue(plan["remote_write_authorized"]); self.assertEqual("merge", plan["merge_method"]); self.assertEqual(["ci"], plan["policy"]["required_checks"]); self.assertEqual(1, plan["policy"]["required_approvals"])

    def test_unprotected_policy_is_rejected(self):
        self.client.branches["main"]["protected"] = False; self.client.rule_rows = []
        with self.assertRaisesRegex(ValueError, "no active protection"): self.prepare()

    def test_linear_history_policy_is_rejected(self):
        self.client.rule_rows.append({"type":"required_linear_history"})
        with self.assertRaisesRegex(ValueError, "unsupported GitHub authority policy"): self.prepare()

    def test_remote_candidate_sha_mismatch_is_rejected(self):
        self.client.branches["devos/candidate"]["commit"]["sha"] = "f"*40
        with self.assertRaisesRegex(ValueError, "exact MASON candidate"): self.prepare()

    def test_open_pr_is_bound_to_exact_candidate(self):
        plan = self.prepare(); binding = open_pr(self.connection,plan["plan_id"],self.client,"2026-09-14T00:03:00Z")["pr"]; self.assertEqual(7,binding["pr_number"]); self.assertEqual(CANDIDATE,binding["head_revision"]); self.assertTrue(open_pr(self.connection,plan["plan_id"],self.client,"later")["replayed"])

    def test_missing_required_check_blocks_ready(self):
        plan = self.prepare(); open_pr(self.connection,plan["plan_id"],self.client,"2026-09-14T00:03:00Z"); self.client.status_row = {"statuses":[]}; ready = verify_ready(self.connection,plan["plan_id"],self.client); self.assertFalse(ready["ready"]); self.assertTrue(any("required check" in r for r in ready["reasons"]))

    def test_policy_drift_blocks_ready(self):
        plan = self.prepare(); open_pr(self.connection,plan["plan_id"],self.client,"2026-09-14T00:03:00Z"); self.client.rule_rows.append({"type":"commit_message_pattern","parameters":{"operator":"starts_with","pattern":"X"}}); ready = verify_ready(self.connection,plan["plan_id"],self.client); self.assertFalse(ready["ready"]); self.assertIn("GitHub policy changed after preparation",ready["reasons"])

    def test_merge_emits_remote_authority_receipt(self):
        plan = self.prepare(); open_pr(self.connection,plan["plan_id"],self.client,"2026-09-14T00:03:00Z"); receipt = merge_remote(self.connection,plan["plan_id"],self.client,"2026-09-14T00:04:00Z")["receipt"]; self.assertEqual("MERGED",receipt["outcome"]); self.assertEqual(MERGE,receipt["authoritative_revision"]); self.assertTrue(receipt["candidate_is_authoritative_parent"]); self.assertEqual("GITHUB_TARGET_BRANCH_UPDATED",receipt["remote_authority_effect"]); self.assertTrue(receipt["remote_write_performed"]); self.assertTrue(merge_remote(self.connection,plan["plan_id"],self.client,"later")["replayed"])

    def test_projection_rebuild_style_reconnect_preserves_receipt(self):
        plan = self.prepare(); open_pr(self.connection,plan["plan_id"],self.client,"2026-09-14T00:03:00Z"); merge_remote(self.connection,plan["plan_id"],self.client,"2026-09-14T00:04:00Z"); self.connection.close(); self.connection = connect_runtime(self.db); self.assertEqual(1,self.connection.execute("SELECT count(*) FROM github_authority_receipts").fetchone()[0])


if __name__ == "__main__": unittest.main()
