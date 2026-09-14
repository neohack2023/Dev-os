#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, sqlite3, urllib.error, urllib.parse, urllib.request
from pathlib import Path

try:
    from .db_runtime import connect_runtime
except ImportError:
    from db_runtime import connect_runtime

DEVOS_ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=DEVOS_ROOT/'state'/'devos-knowledge.db'
API_VERSION='2026-03-10'
REQUIRED_CHECKS=('DevOS Portable Validation / validate','DevOS GitHub Authority Validation / github-authority')

def _canon(v): return json.dumps(v,sort_keys=True,separators=(',',':'))
def _digest(v): return hashlib.sha256(_canon(v).encode()).hexdigest()
def _id(prefix,v): return prefix+':'+_digest(v)[:24]

class GitHubPolicyClient:
    def __init__(self,token,api_base='https://api.github.com'):
        if not token.strip(): raise ValueError('GitHub token is required')
        self.token=token.strip(); self.api_base=api_base.rstrip('/')
    def request(self,method,path,body=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(self.api_base+path,data=data,method=method,headers={'Accept':'application/vnd.github+json','Authorization':f'Bearer {self.token}','X-GitHub-Api-Version':API_VERSION,'User-Agent':'DevOS-GitHub-Policy','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                raw=r.read(); return {} if not raw else json.loads(raw.decode())
        except urllib.error.HTTPError as exc:
            raw=exc.read().decode('utf-8','replace')
            try: msg=json.loads(raw).get('message',raw)
            except json.JSONDecodeError: msg=raw
            raise ValueError(f'GitHub API {method} {path} failed ({exc.code}): {msg}') from exc
    def branch(self,repo,branch): return self.request('GET',f'/repos/{repo}/branches/{urllib.parse.quote(branch,safe="")}')
    def rules(self,repo,branch):
        try:
            x=self.request('GET',f'/repos/{repo}/rules/branches/{urllib.parse.quote(branch,safe="")}?per_page=100')
            return x if isinstance(x,list) else []
        except ValueError as exc:
            if '(403)' in str(exc) or '(404)' in str(exc): return []
            raise
    def protection(self,repo,branch):
        try:
            x=self.request('GET',f'/repos/{repo}/branches/{urllib.parse.quote(branch,safe="")}/protection')
            return x if isinstance(x,dict) else None
        except ValueError as exc:
            if '(403)' in str(exc) or '(404)' in str(exc): return None
            raise
    def apply_branch_protection(self,repo,branch,checks,approvals):
        body={'required_status_checks':{'strict':True,'contexts':list(checks)},'enforce_admins':True,'required_pull_request_reviews':{'dismiss_stale_reviews':True,'require_code_owner_reviews':False,'required_approving_review_count':approvals},'restrictions':None,'allow_force_pushes':False,'allow_deletions':False,'required_conversation_resolution':True}
        return self.request('PUT',f'/repos/{repo}/branches/{urllib.parse.quote(branch,safe="")}/protection',body)

def observe(client,repo,branch):
    b=client.branch(repo,branch); rules=client.rules(repo,branch); protection=client.protection(repo,branch)
    rule_types=sorted({str(r.get('type','')) for r in rules if r.get('type')})
    checks=set(); approvals=0; requires_pr='pull_request' in rule_types
    for r in rules:
        p=r.get('parameters') or {}
        if r.get('type')=='required_status_checks':
            for x in p.get('required_status_checks',[]):
                c=str(x.get('context','')).strip()
                if c: checks.add(c)
        if r.get('type')=='pull_request': approvals=max(approvals,int(p.get('required_approving_review_count',0) or 0))
    if protection:
        rs=protection.get('required_status_checks') or {}
        for c in rs.get('contexts',[]) or []:
            if str(c).strip(): checks.add(str(c).strip())
        for x in rs.get('checks',[]) or []:
            c=str(x.get('context','')).strip()
            if c: checks.add(c)
        rr=protection.get('required_pull_request_reviews') or {}
        if rr: requires_pr=True; approvals=max(approvals,int(rr.get('required_approving_review_count',0) or 0))
    capability='RULESET' if rules else ('BRANCH_PROTECTION' if bool(b.get('protected')) or protection else 'UNPROTECTED')
    policy={'repository':repo,'target_branch':branch,'capability':capability,'protected':bool(b.get('protected')),'rule_types':rule_types,'requires_pull_request':requires_pr,'required_checks':sorted(checks),'required_approvals':approvals,'force_pushes_blocked': not bool((protection or {}).get('allow_force_pushes',{}).get('enabled',False)) if protection else None,'deletions_blocked': not bool((protection or {}).get('allow_deletions',{}).get('enabled',False)) if protection else None}
    missing=[c for c in REQUIRED_CHECKS if c not in checks]
    reasons=[]
    if capability=='UNPROTECTED': reasons.append('target branch is unprotected')
    if not requires_pr: reasons.append('pull requests are not required')
    if missing: reasons.append('missing required DevOS checks: '+', '.join(missing))
    if approvals<1: reasons.append('at least one approving review is not required')
    state='COMPLIANT' if not reasons else 'NONCOMPLIANT'
    policy['required_devos_checks']=list(REQUIRED_CHECKS); policy['missing_devos_checks']=missing; policy['compliance_state']=state; policy['reasons']=reasons; policy['policy_digest']=_digest(policy)
    return policy

def audit(connection,client,repo,branch,observed_at):
    p=observe(client,repo,branch); payload={'schema_version':1,'observed_at':observed_at,'policy':p}; payload['audit_id']=_id('github-policy-audit',payload)
    existing=connection.execute('SELECT payload_json FROM github_policy_audits WHERE audit_id=?',(payload['audit_id'],)).fetchone()
    enc=_canon(payload)
    if existing is None:
        connection.execute('INSERT INTO github_policy_audits(audit_id,repository,target_branch,capability,compliance_state,policy_digest,payload_json,observed_at) VALUES (?,?,?,?,?,?,?,?)',(payload['audit_id'],repo,branch,p['capability'],p['compliance_state'],p['policy_digest'],enc,observed_at)); connection.commit()
    elif existing['payload_json']!=enc: raise ValueError('immutable GitHub policy audit conflict')
    return payload

def bootstrap(connection,client,request):
    repo=str(request.get('repository','')).strip(); branch=str(request.get('target_branch','')).strip(); mode=str(request.get('mode','AUDIT_ONLY')).strip(); observed=str(request.get('observed_at','')).strip()
    if not repo or not branch or not observed: raise ValueError('repository, target_branch, and observed_at are required')
    if mode not in {'AUDIT_ONLY','APPLY_AND_VERIFY'}: raise ValueError('mode must be AUDIT_ONLY or APPLY_AND_VERIFY')
    before=audit(connection,client,repo,branch,observed); bp=before['policy']; write=False
    if mode=='AUDIT_ONLY': outcome='COMPLIANT' if bp['compliance_state']=='COMPLIANT' else 'BLOCKED'; after=bp
    else:
        auth=request.get('authorization') or {}
        if auth.get('approved') is not True or auth.get('grant')!='GITHUB_POLICY_ADMIN': raise ValueError('explicit GITHUB_POLICY_ADMIN authorization is required')
        if bp['compliance_state']=='COMPLIANT': outcome='COMPLIANT'; after=bp
        else:
            if bp['capability']=='RULESET': raise ValueError('ruleset policy mutation is not supported by this portable bootstrap; use an administrator-managed ruleset')
            client.apply_branch_protection(repo,branch,REQUIRED_CHECKS,1); write=True; after=observe(client,repo,branch)
            if after['compliance_state']!='COMPLIANT': raise RuntimeError('GitHub policy write did not produce a compliant policy')
            outcome='APPLIED'
    receipt={'schema_version':1,'audit_id':before['audit_id'],'mode':mode,'outcome':outcome,'repository':repo,'target_branch':branch,'before_digest':bp['policy_digest'],'after_digest':after['policy_digest'],'before_policy':bp,'after_policy':after,'observed_at':observed,'administrative_write_performed':write}
    receipt['receipt_id']=_id('github-policy-receipt',receipt); enc=_canon(receipt)
    existing=connection.execute('SELECT payload_json FROM github_policy_receipts WHERE receipt_id=?',(receipt['receipt_id'],)).fetchone()
    if existing is None:
        connection.execute('INSERT INTO github_policy_receipts(receipt_id,audit_id,mode,outcome,repository,target_branch,before_digest,after_digest,payload_json,observed_at,administrative_write_performed) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(receipt['receipt_id'],before['audit_id'],mode,outcome,repo,branch,receipt['before_digest'],receipt['after_digest'],enc,observed,int(write))); connection.commit()
    elif existing['payload_json']!=enc: raise ValueError('immutable GitHub policy receipt conflict')
    return receipt

def main():
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,default=DEFAULT_DB); p.add_argument('--token',default=os.environ.get('GITHUB_TOKEN','')); sp=p.add_subparsers(dest='command',required=True); run=sp.add_parser('run'); run.add_argument('request',type=Path); args=p.parse_args()
    c=connect_runtime(args.db)
    try:
        client=GitHubPolicyClient(args.token); req=json.loads(args.request.read_text()); print(json.dumps(bootstrap(c,client,req),indent=2,sort_keys=True))
    finally: c.close()
if __name__=='__main__': main()
