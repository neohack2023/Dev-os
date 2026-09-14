from __future__ import annotations
import tempfile, unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'runtime'))
from db_runtime import CURRENT_SCHEMA_VERSION, connect_runtime
from github_policy_bootstrap import REQUIRED_CHECKS, bootstrap, observe

class FakePolicyGitHub:
    def __init__(self,mode='unprotected'):
        self.mode=mode; self.applied=False
    def branch(self,repo,branch):
        protected=self.mode in {'protected','strong','ruleset'} or self.applied
        return {'protected':protected,'commit':{'sha':'a'*40}}
    def rules(self,repo,branch):
        if self.mode!='ruleset': return []
        return [
            {'type':'pull_request','parameters':{'required_approving_review_count':2}},
            {'type':'required_status_checks','parameters':{'required_status_checks':[{'context':c} for c in REQUIRED_CHECKS+('security-scan',)]}},
        ]
    def protection(self,repo,branch):
        if self.mode=='ruleset': return None
        if not (self.mode in {'protected','strong'} or self.applied): return None
        checks=list(REQUIRED_CHECKS)
        approvals=2 if self.mode=='strong' else 1
        if self.mode=='strong': checks.append('security-scan')
        return {'required_status_checks':{'contexts':checks},'required_pull_request_reviews':{'required_approving_review_count':approvals},'allow_force_pushes':{'enabled':False},'allow_deletions':{'enabled':False}}
    def apply_branch_protection(self,repo,branch,checks,approvals):
        self.applied=True; return {'ok':True}

class GitHubPolicyBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'p.db'; self.c=connect_runtime(self.db); self.addCleanup(self.c.close)
    def request(self,mode='AUDIT_ONLY'):
        r={'repository':'owner/repo','target_branch':'main','mode':mode,'observed_at':'2026-09-14T00:20:00Z'}
        if mode=='APPLY_AND_VERIFY': r['authorization']={'grant':'GITHUB_POLICY_ADMIN','approved':True}
        return r
    def test_schema_v8_and_unprotected_audit_blocks_without_writing(self):
        self.assertEqual(8,CURRENT_SCHEMA_VERSION)
        out=bootstrap(self.c,FakePolicyGitHub(),self.request())
        self.assertEqual('BLOCKED',out['outcome']); self.assertFalse(out['administrative_write_performed']); self.assertEqual('UNPROTECTED',out['before_policy']['capability'])
    def test_apply_requires_separate_admin_authorization(self):
        req=self.request('APPLY_AND_VERIFY'); req.pop('authorization')
        with self.assertRaisesRegex(ValueError,'GITHUB_POLICY_ADMIN'): bootstrap(self.c,FakePolicyGitHub(),req)
    def test_branch_protection_is_applied_then_reverified(self):
        client=FakePolicyGitHub(); out=bootstrap(self.c,client,self.request('APPLY_AND_VERIFY'))
        self.assertEqual('APPLIED',out['outcome']); self.assertTrue(out['administrative_write_performed']); self.assertEqual('COMPLIANT',out['after_policy']['compliance_state'])
    def test_stronger_existing_policy_is_preserved_without_write(self):
        client=FakePolicyGitHub('strong'); out=bootstrap(self.c,client,self.request('APPLY_AND_VERIFY'))
        self.assertEqual('COMPLIANT',out['outcome']); self.assertFalse(out['administrative_write_performed']); self.assertIn('security-scan',out['after_policy']['required_checks']); self.assertEqual(2,out['after_policy']['required_approvals'])
    def test_ruleset_is_observed_but_not_rewritten(self):
        client=FakePolicyGitHub('ruleset'); policy=observe(client,'owner/repo','main'); self.assertEqual('RULESET',policy['capability']); self.assertEqual('COMPLIANT',policy['compliance_state'])
        client2=FakePolicyGitHub('ruleset'); client2.rules=lambda repo,branch:[{'type':'pull_request','parameters':{'required_approving_review_count':1}}]
        with self.assertRaisesRegex(ValueError,'ruleset policy mutation is not supported'): bootstrap(self.c,client2,self.request('APPLY_AND_VERIFY'))
    def test_receipts_are_durable(self):
        out=bootstrap(self.c,FakePolicyGitHub(),self.request()); self.assertEqual(1,self.c.execute('SELECT count(*) FROM github_policy_receipts WHERE receipt_id=?',(out['receipt_id'],)).fetchone()[0])

if __name__=='__main__': unittest.main()
