#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sqlite3, sys, hashlib
from dataclasses import asdict
from pathlib import Path
try:
    from .db_runtime import connect_runtime
    from .learning_threshold import MemoryType, EvaluationTier, FixtureResult, assess_evaluation, build_capability, consolidate_experience, consolidate_procedure
except ImportError:
    from db_runtime import connect_runtime
    from learning_threshold import MemoryType, EvaluationTier, FixtureResult, assess_evaluation, build_capability, consolidate_experience, consolidate_procedure

DEVOS_ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DB=DEVOS_ROOT/"state"/"devos-knowledge.db"

def _canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"))
def _immutable(connection,table,key_col,key,payload):
    row=connection.execute(f"SELECT payload_json FROM {table} WHERE {key_col}=?",(key,)).fetchone()
    encoded=_canon(payload)
    if row is not None:
        if row[0]!=encoded: raise ValueError(f"immutable learning conflict: {table}.{key}")
        return
    connection.execute(f"INSERT INTO {table}({key_col},payload_json) VALUES (?,?)",(key,encoded))

def _reflection_context(connection,reflection_ids):
    refs=set(); branches=set()
    for rid in reflection_ids:
        row=connection.execute("SELECT branch_key,payload_json FROM reflection_candidates WHERE reflection_id=?",(rid,)).fetchone()
        if row is None: raise ValueError(f"unknown reflection_id: {rid}")
        branches.add(row["branch_key"])
        payload=json.loads(row["payload_json"])
        refs.update(payload.get("source_evidence_refs",[]))
    return branches,refs

def admit_bundle(connection,bundle):
    observed_at=str(bundle.get("observed_at","")).strip()
    if not observed_at: raise ValueError("observed_at is required")
    p=bundle.get("procedure") or {}
    procedure=consolidate_procedure(
        branch_scope=p["branch_scope"],name=p["name"],version=p["version"],
        trigger_conditions=p["trigger_conditions"],input_schema=p["input_schema"],output_schema=p["output_schema"],
        implementation_ref=p["implementation_ref"],source_reflection_ids=p["source_reflection_ids"],source_evidence_refs=p["source_evidence_refs"],
        preconditions=p.get("preconditions",[]),known_failures=p.get("known_failures",[]),rollback_ref=p.get("rollback_ref","")
    )
    branches,allowed=_reflection_context(connection,procedure.source_reflection_ids)
    if procedure.branch_scope not in branches: raise ValueError("procedure branch_scope is not represented by source reflections")
    if not set(procedure.source_evidence_refs).issubset(allowed): raise ValueError("procedure evidence exceeds source reflection evidence")
    eval_rows=[]
    for row in bundle.get("evaluation",{}).get("results",[]):
        eval_rows.append(FixtureResult(str(row["fixture_id"]),EvaluationTier(str(row["tier"])),bool(row["passed"]),str(row["input_identity"]),str(row.get("observed","")),str(row.get("expected",""))))
    report=assess_evaluation(procedure.procedure_id,eval_rows)
    c=bundle.get("capability") or {}
    capability=build_capability(capability_key=c["capability_key"],description=c["description"],procedure=procedure,report=report,known_tasks=c.get("known_tasks",[]),known_failure_modes=c.get("known_failure_modes",[]))
    e=bundle.get("experience") or {}
    experience=consolidate_experience(memory_type=MemoryType(e["memory_type"]),branch_scope=procedure.branch_scope,statement=e["statement"],source_reflection_ids=procedure.source_reflection_ids,source_evidence_refs=procedure.source_evidence_refs,procedure_id=procedure.procedure_id,capability_id=capability.capability_id)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _immutable(connection,"learning_procedures","procedure_id",procedure.procedure_id,asdict(procedure))
        for rid in procedure.source_reflection_ids:
            connection.execute("INSERT OR IGNORE INTO procedure_reflections(procedure_id,reflection_id) VALUES (?,?)",(procedure.procedure_id,rid))
        eval_payload={"procedure_id":report.procedure_id,"results":[{**asdict(r),"tier":r.tier.value} for r in report.results],"validated_for_transfer":report.validated_for_transfer,"regression_safe":report.regression_safe,"canary_validated":report.canary_validated,"authority_effect":"NONE","promotion_state":"CANDIDATE_ONLY"}
        evaluation_id="evaluation:"+hashlib.sha256(_canon(eval_payload).encode()).hexdigest()[:24]
        _immutable(connection,"learning_evaluations","evaluation_id",evaluation_id,eval_payload)
        connection.execute("INSERT OR IGNORE INTO evaluation_procedures(evaluation_id,procedure_id) VALUES (?,?)",(evaluation_id,procedure.procedure_id))
        _immutable(connection,"learning_experiences","memory_id",experience.memory_id,{**asdict(experience),"memory_type":experience.memory_type.value})
        for rid in experience.source_reflection_ids:
            connection.execute("INSERT OR IGNORE INTO experience_reflections(memory_id,reflection_id) VALUES (?,?)",(experience.memory_id,rid))
        cap_payload={**asdict(capability),"maturity_stage":capability.maturity_stage.value}
        connection.execute("INSERT INTO learning_capabilities(capability_id,payload_json) VALUES (?,?) ON CONFLICT(capability_id) DO UPDATE SET payload_json=excluded.payload_json",(capability.capability_id,_canon(cap_payload)))
        previous=connection.execute("SELECT event_id,event_sequence,payload_json FROM learning_capability_events WHERE capability_id=? ORDER BY event_sequence DESC LIMIT 1",(capability.capability_id,)).fetchone()
        event_state={"capability":cap_payload,"evaluation_id":evaluation_id,"observed_at":observed_at,"authority_effect":"NONE","promotion_state":"CANDIDATE_ONLY"}
        replayed=False
        if previous is not None:
            prior=json.loads(previous["payload_json"])
            prior_state={k:prior.get(k) for k in event_state}
            if prior_state==event_state:
                event_id=previous["event_id"]; replayed=True
        if not replayed:
            seq=(previous["event_sequence"]+1) if previous else 1; pred=previous["event_id"] if previous else ""
            event_payload={**event_state,"event_sequence":seq,"predecessor_event_id":pred}
            event_id="capability-event:"+hashlib.sha256(_canon(event_payload).encode()).hexdigest()[:24]
            connection.execute("INSERT INTO learning_capability_events(event_id,capability_id,event_sequence,observed_at,predecessor_event_id,payload_json) VALUES (?,?,?,?,?,?)",(event_id,capability.capability_id,seq,observed_at,pred,_canon(event_payload)))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    return {"procedure_id":procedure.procedure_id,"evaluation_id":evaluation_id,"memory_id":experience.memory_id,"capability_id":capability.capability_id,"capability_event_id":event_id,"replayed":replayed,"maturity_stage":capability.maturity_stage.value,"validated_for_transfer":report.validated_for_transfer,"regression_safe":report.regression_safe,"canary_validated":report.canary_validated,"authority_effect":"NONE","promotion_state":"CANDIDATE_ONLY"}

def list_learning(connection,branch=None):
    procedures=[]
    for row in connection.execute("SELECT procedure_id,payload_json FROM learning_procedures ORDER BY procedure_id"):
        payload=json.loads(row["payload_json"])
        if branch is None or payload.get("branch_scope")==branch: procedures.append({"procedure_id":row["procedure_id"],**payload})
    experiences=[]
    for row in connection.execute("SELECT memory_id,payload_json FROM learning_experiences ORDER BY memory_id"):
        payload=json.loads(row["payload_json"])
        if branch is None or payload.get("branch_scope")==branch: experiences.append({"memory_id":row["memory_id"],**payload})
    caps=[]
    for row in connection.execute("SELECT capability_id,payload_json FROM learning_capabilities ORDER BY capability_id"):
        payload=json.loads(row["payload_json"])
        if branch is None or payload.get("branch_scope")==branch: caps.append({"capability_id":row["capability_id"],**payload})
    return {"procedures":procedures,"experiences":experiences,"capabilities":caps}

def main():
    parser=argparse.ArgumentParser(description="Portable DevOS governed learning store")
    parser.add_argument("--db",type=Path,default=DEFAULT_DB)
    sub=parser.add_subparsers(dest="command",required=True)
    a=sub.add_parser("admit"); a.add_argument("input",type=Path)
    l=sub.add_parser("list"); l.add_argument("--branch")
    args=parser.parse_args()
    try:
        connection=connect_runtime(args.db)
        try:
            result=admit_bundle(connection,json.loads(args.input.read_text())) if args.command=="admit" else list_learning(connection,args.branch)
        finally: connection.close()
        print(json.dumps({"ok":True,**result},indent=2,sort_keys=True)); return 0
    except (OSError,KeyError,ValueError,sqlite3.Error,json.JSONDecodeError) as exc:
        print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
