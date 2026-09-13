#!/usr/bin/env python3
"""Deterministic, authority-neutral evidence relations for portable DevOS."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence


class CrossReference(str, Enum):
    NEW = "NEW"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
    INSUFFICIENT = "INSUFFICIENT"


class LineageState(str, Enum):
    INDEPENDENT_ROOT = "INDEPENDENT_ROOT"
    DERIVED = "DERIVED"
    REVISION = "REVISION"
    QUOTATION_OR_SUMMARY = "QUOTATION_OR_SUMMARY"
    SHARED_ROOT = "SHARED_ROOT"
    REPRODUCTION_SAME_INPUTS = "REPRODUCTION_SAME_INPUTS"
    REPLICATION_NEW_INPUTS = "REPLICATION_NEW_INPUTS"
    PARTIAL_SHARED_INPUT = "PARTIAL_SHARED_INPUT"
    UNKNOWN_LINEAGE = "UNKNOWN_LINEAGE"


class TriangulationState(str, Enum):
    CONVERGENCE = "CONVERGENCE"
    DIVERGENCE = "DIVERGENCE"
    SINGLETON = "SINGLETON"
    ORTHOGONAL = "ORTHOGONAL"
    INSUFFICIENT = "INSUFFICIENT"


COUNTABLE_INDEPENDENT_STATES = {
    LineageState.INDEPENDENT_ROOT,
    LineageState.REPLICATION_NEW_INPUTS,
}
DERIVATIVE_STATES = {
    LineageState.DERIVED,
    LineageState.REVISION,
    LineageState.QUOTATION_OR_SUMMARY,
    LineageState.SHARED_ROOT,
    LineageState.REPRODUCTION_SAME_INPUTS,
}


@dataclass(frozen=True)
class CurrentClaim:
    claim_id: str
    claim_key: str
    value: str
    lifecycle: str = "active"


@dataclass(frozen=True)
class AtomicFinding:
    finding_id: str
    claim_key: str
    value: str
    evidence_ref: str
    root_ids: tuple[str, ...] = ()
    lineage_state: LineageState = LineageState.UNKNOWN_LINEAGE
    shared_input_keys: tuple[str, ...] = ()
    related_claim_keys: tuple[str, ...] = ()
    supersedes_claim_id: str | None = None


@dataclass(frozen=True)
class FindingAssessment:
    finding: AtomicFinding
    cross_reference: CrossReference
    current_claim_id: str | None


@dataclass(frozen=True)
class RootSummary:
    artifact_count: int
    finding_count: int
    independent_root_ids: tuple[str, ...]
    correlated_root_ids: tuple[str, ...]
    reproduction_root_ids: tuple[str, ...]
    unknown_finding_ids: tuple[str, ...]

    @property
    def independent_root_count(self) -> int:
        return len(self.independent_root_ids)

    @property
    def correlated_root_count(self) -> int:
        return len(self.correlated_root_ids)

    @property
    def reproduction_count(self) -> int:
        return len(self.reproduction_root_ids)

    @property
    def unknown_lineage_count(self) -> int:
        return len(self.unknown_finding_ids)


@dataclass(frozen=True)
class TriangulationResult:
    claim_key: str
    state: TriangulationState
    root_summary: RootSummary
    supporting_root_ids: tuple[str, ...] = ()
    contradicting_root_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeltaPacket:
    delta_id: str
    claim_key: str
    current_claim_id: str | None
    current_value: str | None
    observed_values: tuple[str, ...]
    cross_reference_states: tuple[str, ...]
    triangulation_state: str
    independent_root_count: int
    correlated_root_count: int
    reproduction_count: int
    unknown_lineage_count: int
    evidence_refs: tuple[str, ...]
    material: bool
    recommended_action: str
    authority_effect: str = "NONE"


def _norm(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def cross_reference(finding: AtomicFinding, current_claims: Mapping[str, CurrentClaim]) -> FindingAssessment:
    if not finding.claim_key.strip() or not finding.value.strip():
        return FindingAssessment(finding, CrossReference.INSUFFICIENT, None)
    current = current_claims.get(finding.claim_key)
    if finding.supersedes_claim_id:
        if current and finding.supersedes_claim_id == current.claim_id:
            return FindingAssessment(finding, CrossReference.SUPERSEDES, current.claim_id)
        return FindingAssessment(finding, CrossReference.INSUFFICIENT, current.claim_id if current else None)
    if current is None:
        return FindingAssessment(
            finding,
            CrossReference.PARTIAL_OVERLAP if finding.related_claim_keys else CrossReference.NEW,
            None,
        )
    if _norm(finding.value) == _norm(current.value):
        return FindingAssessment(finding, CrossReference.SUPPORTS, current.claim_id)
    return FindingAssessment(finding, CrossReference.CONTRADICTS, current.claim_id)


def summarize_roots(findings: Sequence[AtomicFinding]) -> RootSummary:
    independent: set[str] = set()
    correlated: set[str] = set()
    reproduction: set[str] = set()
    unknown: set[str] = set()
    for finding in findings:
        roots = set(finding.root_ids)
        state = finding.lineage_state
        if state in COUNTABLE_INDEPENDENT_STATES:
            independent.update(roots)
        elif state == LineageState.PARTIAL_SHARED_INPUT:
            correlated.update(roots)
        elif state == LineageState.REPRODUCTION_SAME_INPUTS:
            reproduction.update(roots)
        elif state == LineageState.UNKNOWN_LINEAGE or not roots:
            unknown.add(finding.finding_id)
        elif state in DERIVATIVE_STATES:
            continue
    independent.difference_update(correlated)
    return RootSummary(
        artifact_count=len(findings),
        finding_count=len(findings),
        independent_root_ids=tuple(sorted(independent)),
        correlated_root_ids=tuple(sorted(correlated)),
        reproduction_root_ids=tuple(sorted(reproduction)),
        unknown_finding_ids=tuple(sorted(unknown)),
    )


def triangulate(assessments: Sequence[FindingAssessment], *, claim_key: str) -> TriangulationResult:
    scoped = [a for a in assessments if a.finding.claim_key == claim_key]
    if not scoped:
        return TriangulationResult(
            claim_key=claim_key,
            state=TriangulationState.ORTHOGONAL if assessments else TriangulationState.INSUFFICIENT,
            root_summary=summarize_roots([]),
            notes=("no findings address requested claim_key",),
        )
    summary = summarize_roots([a.finding for a in scoped])
    support_roots: set[str] = set()
    contradict_roots: set[str] = set()
    for assessment in scoped:
        if assessment.finding.lineage_state not in COUNTABLE_INDEPENDENT_STATES:
            continue
        if assessment.cross_reference in {CrossReference.SUPPORTS, CrossReference.NEW, CrossReference.SUPERSEDES}:
            support_roots.update(assessment.finding.root_ids)
        elif assessment.cross_reference == CrossReference.CONTRADICTS:
            contradict_roots.update(assessment.finding.root_ids)
    support_roots.difference_update(summary.correlated_root_ids)
    contradict_roots.difference_update(summary.correlated_root_ids)
    notes: list[str] = []
    if summary.unknown_lineage_count:
        notes.append("unknown lineage present; strong convergence is blocked")
    if summary.correlated_root_count:
        notes.append("partial shared-input correlation present")
    if support_roots and contradict_roots:
        state = TriangulationState.DIVERGENCE
    elif summary.unknown_lineage_count and summary.independent_root_count < 2:
        state = TriangulationState.INSUFFICIENT
    elif len(support_roots) >= 2 or len(contradict_roots) >= 2:
        state = TriangulationState.CONVERGENCE
    elif len(support_roots | contradict_roots) == 1:
        state = TriangulationState.SINGLETON
    else:
        state = TriangulationState.INSUFFICIENT
    return TriangulationResult(
        claim_key=claim_key,
        state=state,
        root_summary=summary,
        supporting_root_ids=tuple(sorted(support_roots)),
        contradicting_root_ids=tuple(sorted(contradict_roots)),
        notes=tuple(notes),
    )


def build_delta_packet(
    assessments: Sequence[FindingAssessment],
    triangulation: TriangulationResult,
    current_claims: Mapping[str, CurrentClaim],
) -> DeltaPacket:
    claim_key = triangulation.claim_key
    scoped = [a for a in assessments if a.finding.claim_key == claim_key]
    current = current_claims.get(claim_key)
    values = tuple(sorted({_norm(a.finding.value) for a in scoped if a.finding.value.strip()}))
    states = tuple(sorted({a.cross_reference.value for a in scoped}))
    refs = tuple(sorted({a.finding.evidence_ref for a in scoped if a.finding.evidence_ref}))
    material = bool({CrossReference.NEW.value, CrossReference.CONTRADICTS.value, CrossReference.SUPERSEDES.value}.intersection(states)) and triangulation.state not in {TriangulationState.INSUFFICIENT, TriangulationState.ORTHOGONAL}
    if triangulation.state == TriangulationState.DIVERGENCE:
        action = "REVIEW_CONFLICT"
    elif not material:
        action = "NO_PROMOTION"
    elif CrossReference.SUPERSEDES.value in states:
        action = "REVIEW_SUPERSESSION"
    elif CrossReference.CONTRADICTS.value in states:
        action = "REVIEW_CONTRADICTION"
    elif CrossReference.NEW.value in states:
        action = "REVIEW_NEW_CLAIM"
    else:
        action = "NO_PROMOTION"
    payload = {
        "claim_key": claim_key,
        "current_claim_id": current.claim_id if current else None,
        "current_value": _norm(current.value) if current else None,
        "observed_values": values,
        "cross_reference_states": states,
        "triangulation_state": triangulation.state.value,
        "independent_root_count": triangulation.root_summary.independent_root_count,
        "correlated_root_count": triangulation.root_summary.correlated_root_count,
        "reproduction_count": triangulation.root_summary.reproduction_count,
        "unknown_lineage_count": triangulation.root_summary.unknown_lineage_count,
        "evidence_refs": refs,
        "material": material,
        "recommended_action": action,
        "authority_effect": "NONE",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return DeltaPacket(delta_id="delta-" + hashlib.sha256(canonical.encode()).hexdigest()[:16], **payload)


def packet_to_json(packet: DeltaPacket) -> str:
    return json.dumps(asdict(packet), indent=2, sort_keys=True)
