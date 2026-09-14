from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from build_knowledge_db import build
from db_runtime import CURRENT_SCHEMA_VERSION, connect_runtime
from mason_execution import apply_execution, compute_change_digest, prepare_execution

HOST_FIXTURE = ROOT / "tests" / "fixtures" / "knowledge_db" / "host"

class MasonExecutionTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> str:
        result=subprocess.run(["git","-C",str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True); return result.stdout.strip()
    def _repo(self, *, extra_path: bool=False):
        repo=Path(self.temp.name)/"repo"; repo.mkdir(); self._git(repo,"init","-b","main"); self._git(repo,"config","user.email","devos@example.invalid"); self._git(repo,"config","user.name","DevOS Fixture"); (repo/"src").mkdir(); (repo/"src"/"value.txt").write_text("base\n"); self._git(repo,"add","."); self._git(repo,"commit","-m","base"); base=self._git(repo,"rev-parse","HEAD"); (repo/"src"/"value.txt").write_text("candidate\n")
        if extra_path:(repo/"outside.txt").write_text("unexpected\n")
        self._git(repo,"add","."); self._git(repo,"commit","-m","candidate"); candidate=self._git(repo,"rev-parse","HEAD"); digest=compute_change_digest(repo,base,candidate); self._git(repo,"reset","--hard",base); return repo,base,candidate,digest
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.db=Path(self.temp.name)/"mason.db"; self.connection=connect_runtime(self.db); self.addCleanup(self.connection.close)
    def _seed_handoff(self,candidate,digest,*,outcome="PROMOTE",target_paths=None):
        capability_id="capability:fixture"; envelope_id="promotion-envelope:fixture"; decision_id=f"promotion-decision:{outcome.lower()}"; self.connection.execute("INSERT OR REPLACE INTO learning_capabilities(capability_id,payload_json) VALUES (?,?)",(capability_id,json.dumps({"capability_id":capability_id,"branch_scope":"project-core","maturity_stage":"TRANSFER"},sort_keys=True,separators=(",",":"))))
        envelope={"schema_version":1,"envelope_id":envelope_id,"candidate_revision":candidate,"change_digest":digest,"target":{"repository":"owner/fixture","branch":"main","paths":target_paths or ["src/value.txt"],"change_ref":f"git:{candidate}"},"required_authorization":"reviewed repository change","stone_state":"LOCKED","mason_state":"HANDOFF_REQUIRED","write_authorized":False}
        self.connection.execute("INSERT OR REPLACE INTO promotion_envelopes(envelope_id,capability_id,branch_scope,candidate_revision,change_digest,stone_state,mason_state,payload_json,observed_at,authority_effect,write_authorized) VALUES (?,?,?,?,?,?,?,?,?,?,0)",(envelope_id,capability_id,"project-core",candidate,digest,"LOCKED","HANDOFF_REQUIRED",json.dumps(envelope,sort_keys=True,separators=(",",":")),"2026-09-13T23:40:00+00:00","NONE"))
        decision={"schema_version":1,"decision_id":decision_id,"envelope_id":envelope_id,"candidate_revision":candidate,"outcome":outcome,"next_action":"MASON_REVIEW_PROMOTION" if outcome=="PROMOTE" else "REVISE_CANDIDATE","write_authorized":False}
        self.connection.execute("INSERT OR REPLACE INTO promotion_decisions(decision_id,envelope_id,outcome,candidate_revision,verifier_digest,payload_json,observed_at,authority_effect,write_authorized) VALUES (?,?,?,?,?,?,?,?,0)",(decision_id,envelope_id,outcome,candidate,"f"*64,json.dumps(decision,sort_keys=True,separators=(",",":")),"2026-09-13T23:41:00+00:00","NONE")); self.connection.commit(); return decision_id,envelope_id
    def _request(self,decision_id,envelope_id,candidate,base):
        return {"observed_at":"2026-09-13T23:42:00+00:00","base_revision":base,"authorization":{"authorization_id":"authorization:fixture","source":"fixture-operator","actor":"fixture-reviewer","observed_at":"2026-09-13T23:42:00+00:00","grant":"MASON_FAST_FORWARD","decision_id":decision_id,"envelope_id":envelope_id,"candidate_revision":candidate,"target_branch":"main","scope":"reviewed repository change","approved":True}}
    def test_schema_v9_and_prepare_is_local_only(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); result=prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base)); self.assertEqual(9,CURRENT_SCHEMA_VERSION); self.assertFalse(result["plan"]["remote_write_authorized"]); self.assertFalse(result["plan"]["remote_write_performed"]); self.assertEqual(["src/value.txt"],result["plan"]["changed_paths"])
    def test_apply_fast_forwards_and_emits_verified_receipt(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); plan=prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))["plan"]; receipt=apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:43:00+00:00")["receipt"]; self.assertEqual("APPLIED",receipt["outcome"]); self.assertEqual(candidate,self._git(repo,"rev-parse","HEAD")); self.assertEqual(candidate,receipt["post_revision"]); self.assertEqual("LOCAL_GIT_REF_UPDATED",receipt["local_authority_effect"]); self.assertEqual("NONE",receipt["remote_authority_effect"]); self.assertFalse(receipt["remote_write_performed"]); self.assertTrue(receipt["working_tree_clean"])
    def test_exact_apply_replay_is_idempotent(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); plan=prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))["plan"]; first=apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:43:00+00:00"); second=apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:44:00+00:00"); self.assertFalse(first["replayed"]); self.assertTrue(second["replayed"]); self.assertEqual(first["receipt"]["receipt_id"],second["receipt"]["receipt_id"]); self.assertEqual(1,self.connection.execute("SELECT count(*) FROM mason_execution_receipts").fetchone()[0])
    def test_non_promote_decision_is_rejected(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest,outcome="REVISE")
        with self.assertRaisesRegex(ValueError,"PROMOTE"): prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))
    def test_authorization_must_match_locked_handoff(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); request=self._request(decision_id,envelope_id,candidate,base); request["authorization"]["candidate_revision"]="a"*40
        with self.assertRaisesRegex(ValueError,"authorization candidate_revision"): prepare_execution(self.connection,decision_id,repo,request)
    def test_dirty_worktree_is_rejected(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); (repo/"dirty.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ValueError,"dirty Git worktree"): prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))
    def test_changed_path_escape_is_rejected(self):
        repo,base,candidate,digest=self._repo(extra_path=True); decision_id,envelope_id=self._seed_handoff(candidate,digest)
        with self.assertRaisesRegex(ValueError,"changed-path set"): prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))
    def test_digest_mismatch_is_rejected(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,"b"*64)
        with self.assertRaisesRegex(ValueError,"diff digest"): prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))
    def test_active_smudge_filter_is_rejected(self):
        repo,base,candidate,digest=self._repo(); self._git(repo,"config","filter.evil.smudge","sh -c 'echo nope'"); decision_id,envelope_id=self._seed_handoff(candidate,digest)
        with self.assertRaisesRegex(ValueError,"smudge/process"): prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))
    def test_failed_apply_writes_one_failure_receipt(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); plan=prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))["plan"]; (repo/"dirty.txt").write_text("drift\n")
        with self.assertRaisesRegex(RuntimeError,"immutable receipt"): apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:43:00+00:00")
        row=self.connection.execute("SELECT outcome,payload_json FROM mason_execution_receipts WHERE plan_id=?",(plan["plan_id"],)).fetchone(); self.assertEqual("FAILED",row["outcome"]); self.assertEqual("NONE",json.loads(row["payload_json"])["local_authority_effect"])
        with self.assertRaisesRegex(RuntimeError,"previously failed"): apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:44:00+00:00")
        self.assertEqual(1,self.connection.execute("SELECT count(*) FROM mason_execution_receipts WHERE plan_id=?",(plan["plan_id"],)).fetchone()[0])
    def test_projection_rebuild_preserves_execution_receipt(self):
        repo,base,candidate,digest=self._repo(); decision_id,envelope_id=self._seed_handoff(candidate,digest); plan=prepare_execution(self.connection,decision_id,repo,self._request(decision_id,envelope_id,candidate,base))["plan"]; apply_execution(self.connection,plan["plan_id"],repo,"2026-09-13T23:43:00+00:00"); self.connection.close(); build(HOST_FIXTURE/"Devos",HOST_FIXTURE,self.db); self.connection=connect_runtime(self.db); self.addCleanup(self.connection.close); self.assertEqual(1,self.connection.execute("SELECT count(*) FROM mason_execution_plans").fetchone()[0]); self.assertEqual(1,self.connection.execute("SELECT count(*) FROM mason_execution_receipts").fetchone()[0])
if __name__=="__main__": unittest.main()
