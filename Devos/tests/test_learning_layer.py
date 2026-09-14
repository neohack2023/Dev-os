from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; RUNTIME=ROOT/"runtime"; sys.path.insert(0,str(RUNTIME))
from build_knowledge_db import build
from db_runtime import CURRENT_SCHEMA_VERSION, connect_runtime
from evidence_store import persist_episode
from reflection_store import persist_reflection
from learning_threshold import EvaluationTier, FixtureResult, assess_evaluation, maturity_from_report
from learning_store import admit_bundle

FIXTURE=ROOT/"tests"/"fixtures"/"knowledge_db"/"host"
EPISODE=ROOT/"tests"/"fixtures"/"evidence"/"episode-convergence.json"
REFLECT=ROOT/"tests"/"fixtures"/"reflection"/"request-lantern.json"

class LearningLayerTests(unittest.TestCase):
    def make_context(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db=Path(temp.name)/"learning.db"; build(FIXTURE/"Devos",FIXTURE,db,fresh=True)
        c=connect_runtime(db)
        episode=json.loads(EPISODE.read_text()); evidence=persist_episode(c,episode)
        request=json.loads(REFLECT.read_text()); reflected=persist_reflection(c,evidence["delta"]["delta_id"],request)
        return db,c,reflected["reflection"]
    def bundle(self, reflection):
        refs=list(reflection["source_evidence_refs"])
        return {
          "observed_at":"2026-09-13T23:12:00+00:00",
          "procedure":{"branch_scope":"feature-lantern","name":"lantern-stability-check","version":"1","trigger_conditions":["lantern state available"],"input_schema":["state"],"output_schema":["stable"],"implementation_ref":"tests:lantern_stability_check","source_reflection_ids":[reflection["reflection_id"]],"source_evidence_refs":refs,"known_failures":["hidden mutable ordering"]},
          "evaluation":{"results":[
            {"fixture_id":"inv","tier":"T0","passed":True,"input_identity":"contract"},
            {"fixture_id":"known","tier":"T1","passed":True,"input_identity":"fixture-A"},
            {"fixture_id":"dev","tier":"T2","passed":True,"input_identity":"fixture-B"},
            {"fixture_id":"holdout","tier":"T3","passed":True,"input_identity":"fixture-C"},
            {"fixture_id":"regression","tier":"T4","passed":True,"input_identity":"fixture-R"},
            {"fixture_id":"canary","tier":"T5","passed":True,"input_identity":"real-canary"}]},
          "capability":{"capability_key":"lantern.stability","description":"Recognize deterministic lantern state across unseen inputs.","known_tasks":["lantern stability"],"known_failure_modes":["hidden mutable ordering"]},
          "experience":{"memory_type":"PROCEDURAL","statement":"Lantern stability procedure transferred to a held-out input and passed regression plus canary checks."}
        }
    def test_schema_v7_and_learning_admission(self):
        db,c,r=self.make_context()
        try:
            self.assertEqual(7,CURRENT_SCHEMA_VERSION)
            out=admit_bundle(c,self.bundle(r))
            self.assertEqual("TRANSFER",out["maturity_stage"]); self.assertTrue(out["validated_for_transfer"]); self.assertTrue(out["regression_safe"]); self.assertTrue(out["canary_validated"]); self.assertEqual("NONE",out["authority_effect"])
        finally:c.close()
    def test_learning_replay_is_idempotent(self):
        db,c,r=self.make_context()
        try:
            b=self.bundle(r); first=admit_bundle(c,b); second=admit_bundle(c,b)
            self.assertEqual(first["procedure_id"],second["procedure_id"])
            self.assertFalse(first["replayed"]); self.assertTrue(second["replayed"])
            self.assertEqual(first["capability_event_id"],second["capability_event_id"])
            self.assertEqual(1,c.execute("SELECT count(*) FROM learning_capability_events").fetchone()[0])
        finally:c.close()
    def test_learning_cannot_invent_evidence(self):
        db,c,r=self.make_context()
        try:
            b=self.bundle(r); b["procedure"]["source_evidence_refs"].append("invented://support")
            with self.assertRaisesRegex(ValueError,"evidence exceeds"): admit_bundle(c,b)
        finally:c.close()
    def test_transfer_requires_disjoint_holdout_identity(self):
        rows=[FixtureResult("a",EvaluationTier.T0,True,"contract"),FixtureResult("b",EvaluationTier.T1,True,"same"),FixtureResult("c",EvaluationTier.T2,True,"dev"),FixtureResult("d",EvaluationTier.T3,True,"same")]
        with self.assertRaisesRegex(ValueError,"disjoint"): assess_evaluation("procedure:x",rows)
    def test_failed_holdout_caps_maturity_at_reflection(self):
        rows=[FixtureResult("a",EvaluationTier.T0,True,"contract"),FixtureResult("b",EvaluationTier.T1,True,"train"),FixtureResult("c",EvaluationTier.T2,True,"dev"),FixtureResult("d",EvaluationTier.T3,False,"holdout")]
        report=assess_evaluation("procedure:x",rows)
        self.assertEqual("REFLECTION",maturity_from_report(report).value)
    def test_projection_rebuild_preserves_learning(self):
        db,c,r=self.make_context(); out=admit_bundle(c,self.bundle(r)); c.close(); build(FIXTURE/"Devos",FIXTURE,db)
        c=connect_runtime(db)
        try:self.assertEqual(1,c.execute("SELECT count(*) FROM learning_procedures WHERE procedure_id=?",(out["procedure_id"],)).fetchone()[0])
        finally:c.close()

if __name__=="__main__": unittest.main()
