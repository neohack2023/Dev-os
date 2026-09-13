#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib, json
from typing import Mapping, Sequence

AUTHORITY_EFFECT = "NONE"
PROMOTION_STATE = "CANDIDATE_ONLY"

class EvaluationTier(str, Enum):
    T0="T0"; T1="T1"; T2="T2"; T3="T3"; T4="T4"; T5="T5"
class MaturityStage(str, Enum):
    RECALL="RECALL"; RECOGNITION="RECOGNITION"; REFLECTION="REFLECTION"; TRANSFER="TRANSFER"; COMPOSITION="COMPOSITION"; ADAPTATION="ADAPTATION"; METACOGNITIVE_CONTROL="METACOGNITIVE_CONTROL"
class MemoryType(str, Enum):
    EPISODIC="EPISODIC"; SEMANTIC="SEMANTIC"; PROCEDURAL="PROCEDURAL"; NEGATIVE="NEGATIVE"

@dataclass(frozen=True)
class ProcedureSpec:
    branch_scope:str; name:str; version:str; trigger_conditions:tuple[str,...]; input_schema:tuple[str,...]; output_schema:tuple[str,...]; implementation_ref:str; source_reflection_ids:tuple[str,...]; source_evidence_refs:tuple[str,...]; preconditions:tuple[str,...]=(); known_failures:tuple[str,...]=(); rollback_ref:str=""
    @property
    def procedure_id(self)->str:
        return stable_id("procedure", self.__dict__)

@dataclass(frozen=True)
class FixtureResult:
    fixture_id:str; tier:EvaluationTier; passed:bool; input_identity:str; observed:str=""; expected:str=""
@dataclass(frozen=True)
class EvaluationReport:
    procedure_id:str; results:tuple[FixtureResult,...]; authority_effect:str=AUTHORITY_EFFECT; promotion_state:str=PROMOTION_STATE
    @property
    def passed_by_tier(self):
        grouped={}
        for r in self.results: grouped.setdefault(r.tier,[]).append(r.passed)
        return {k:bool(v) and all(v) for k,v in grouped.items()}
    @property
    def validated_for_transfer(self):
        s=self.passed_by_tier
        return all(s.get(t,False) for t in (EvaluationTier.T0,EvaluationTier.T1,EvaluationTier.T2,EvaluationTier.T3))
    @property
    def regression_safe(self): return self.validated_for_transfer and self.passed_by_tier.get(EvaluationTier.T4,False)
    @property
    def canary_validated(self): return self.regression_safe and self.passed_by_tier.get(EvaluationTier.T5,False)

@dataclass(frozen=True)
class ExperienceRecord:
    memory_id:str; memory_type:MemoryType; branch_scope:str; statement:str; source_reflection_ids:tuple[str,...]; source_evidence_refs:tuple[str,...]; procedure_id:str=""; capability_id:str=""; authority_effect:str=AUTHORITY_EFFECT; promotion_state:str=PROMOTION_STATE

@dataclass(frozen=True)
class CapabilityRecord:
    capability_id:str; branch_scope:str; description:str; procedure_ids:tuple[str,...]; known_tasks:tuple[str,...]; known_failure_modes:tuple[str,...]; maturity_stage:MaturityStage; evaluation_profile:tuple[tuple[str,bool],...]; transfer_fixture_ids:tuple[str,...]; regression_safe:bool; canary_validated:bool; authority_effect:str=AUTHORITY_EFFECT; promotion_state:str=PROMOTION_STATE

def stable_id(prefix:str,payload:object)->str:
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=lambda o:o.value if isinstance(o,Enum) else o.__dict__)
    return f"{prefix}:"+hashlib.sha256(raw.encode()).hexdigest()[:24]

def _clean(values:Sequence[str])->tuple[str,...]: return tuple(sorted({v.strip() for v in values if isinstance(v,str) and v.strip()}))

def consolidate_procedure(*,branch_scope:str,name:str,version:str,trigger_conditions:Sequence[str],input_schema:Sequence[str],output_schema:Sequence[str],implementation_ref:str,source_reflection_ids:Sequence[str],source_evidence_refs:Sequence[str],preconditions:Sequence[str]=(),known_failures:Sequence[str]=(),rollback_ref:str="")->ProcedureSpec:
    if not all(x.strip() for x in (branch_scope,name,version,implementation_ref)): raise ValueError("branch_scope, name, version, and implementation_ref are required")
    refs=_clean(source_reflection_ids); evidence=_clean(source_evidence_refs)
    if not refs or not evidence: raise ValueError("procedure requires reflection lineage and evidence")
    if not trigger_conditions or not input_schema or not output_schema: raise ValueError("procedure contract requires triggers, inputs, outputs")
    return ProcedureSpec(branch_scope.strip(),name.strip(),version.strip(),tuple(trigger_conditions),tuple(input_schema),tuple(output_schema),implementation_ref.strip(),refs,evidence,tuple(preconditions),tuple(known_failures),rollback_ref.strip())

def assess_evaluation(procedure_id:str, results:Sequence[FixtureResult])->EvaluationReport:
    if not results: raise ValueError("evaluation requires fixture results")
    ids=[r.fixture_id for r in results]
    if len(ids)!=len(set(ids)): raise ValueError("fixture ids must be unique")
    tiers={r.tier for r in results}
    required={EvaluationTier.T0,EvaluationTier.T1,EvaluationTier.T2,EvaluationTier.T3}
    missing=required-tiers
    if missing: raise ValueError("evaluation missing required tiers: "+",".join(sorted(t.value for t in missing)))
    train={r.input_identity for r in results if r.tier in {EvaluationTier.T1,EvaluationTier.T2}}
    holdout={r.input_identity for r in results if r.tier==EvaluationTier.T3}
    if "" in holdout or train & holdout: raise ValueError("held-out transfer identities must be non-empty and disjoint from train/dev")
    return EvaluationReport(procedure_id,tuple(sorted(results,key=lambda r:(r.tier.value,r.fixture_id))))

def maturity_from_report(report:EvaluationReport)->MaturityStage:
    s=report.passed_by_tier
    if report.validated_for_transfer: return MaturityStage.TRANSFER
    if all(s.get(t,False) for t in (EvaluationTier.T0,EvaluationTier.T1,EvaluationTier.T2)): return MaturityStage.REFLECTION
    if all(s.get(t,False) for t in (EvaluationTier.T0,EvaluationTier.T1)): return MaturityStage.RECOGNITION
    return MaturityStage.RECALL

def build_capability(*,capability_key:str,description:str,procedure:ProcedureSpec,report:EvaluationReport,known_tasks:Sequence[str]=(),known_failure_modes:Sequence[str]=())->CapabilityRecord:
    if report.procedure_id!=procedure.procedure_id: raise ValueError("evaluation report does not belong to procedure")
    cid=stable_id("capability",{"capability_key":capability_key,"branch_scope":procedure.branch_scope})
    transfer=tuple(r.fixture_id for r in report.results if r.tier==EvaluationTier.T3 and r.passed)
    profile=tuple((t.value,p) for t,p in sorted(report.passed_by_tier.items(),key=lambda x:x[0].value))
    return CapabilityRecord(cid,procedure.branch_scope,description.strip(),(procedure.procedure_id,),_clean(known_tasks),_clean(known_failure_modes),maturity_from_report(report),profile,transfer,report.regression_safe,report.canary_validated)

def consolidate_experience(*,memory_type:MemoryType,branch_scope:str,statement:str,source_reflection_ids:Sequence[str],source_evidence_refs:Sequence[str],procedure_id:str="",capability_id:str="")->ExperienceRecord:
    refs=_clean(source_reflection_ids); evidence=_clean(source_evidence_refs)
    if not branch_scope.strip() or not statement.strip() or not refs or not evidence: raise ValueError("experience requires branch, statement, reflection lineage, and evidence")
    if memory_type==MemoryType.PROCEDURAL and not procedure_id.strip(): raise ValueError("procedural memory requires procedure_id")
    payload={"memory_type":memory_type.value,"branch_scope":branch_scope.strip(),"statement":statement.strip(),"source_reflection_ids":refs,"source_evidence_refs":evidence,"procedure_id":procedure_id.strip(),"capability_id":capability_id.strip()}
    return ExperienceRecord(stable_id("memory",payload),memory_type,branch_scope.strip(),statement.strip(),refs,evidence,procedure_id.strip(),capability_id.strip())
