#!/usr/bin/env python3
"""Adapt admitted evidence deltas into authority-neutral reflection candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Mapping

try:
    from .reflection_core import build_reflection_core, canonical_digest, required_text
except ImportError:
    from reflection_core import build_reflection_core, canonical_digest, required_text

DELTA_REFLECTION_SCHEMA = "devos-delta-reflection-candidate/v1"
DELTA_IDENTITY_FIELDS = (
    "claim_key", "current_claim_id", "current_value", "observed_values",
    "cross_reference_states", "triangulation_state", "independent_root_count",
    "correlated_root_count", "reproduction_count", "unknown_lineage_count",
    "evidence_refs", "material", "recommended_action", "authority_effect",
)


@dataclass(frozen=True)
class DeltaReflectionCandidate:
    schema: str
    reflection_id: str
    source_delta_id: str
    source_delta_digest: str
    claim_key: str
    current_claim_id: str | None
    triangulation_state: str
    independent_root_count: int
    correlated_root_count: int
    reproduction_count: int
    unknown_lineage_count: int
    source_evidence_refs: tuple[str, ...]
    source_material: bool
    source_recommended_action: str
    branch_key: str
    observed_symptom: str
    expected_behavior: str
    mechanism_hypothesis: str
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    predicted_consequence: str
    required_disconfirmation_test: str
    proposed_scope: str
    authority_effect: str = "NONE"
    promotion_state: str = "CANDIDATE_ONLY"


def _required_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _string_sequence(mapping: Mapping[str, object], key: str, *, required: bool) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list or tuple of strings")
    items = tuple(sorted({item.strip() for item in value if item.strip()}))
    if required and not items:
        raise ValueError(f"{key} must preserve at least one non-empty reference")
    return items


def expected_delta_id(packet: Mapping[str, object]) -> str:
    payload = {key: packet.get(key) for key in DELTA_IDENTITY_FIELDS}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "delta-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def validate_delta_packet(packet: Mapping[str, object]) -> None:
    if packet.get("authority_effect") != "NONE":
        raise ValueError("source delta must have authority_effect NONE")
    for key in ("delta_id", "claim_key", "triangulation_state", "recommended_action"):
        required_text(packet, key)
    _string_sequence(packet, "observed_values", required=False)
    _string_sequence(packet, "cross_reference_states", required=True)
    _string_sequence(packet, "evidence_refs", required=True)
    if not isinstance(packet.get("material"), bool):
        raise ValueError("source delta material must be boolean")
    for key in ("independent_root_count", "correlated_root_count", "reproduction_count", "unknown_lineage_count"):
        _required_int(packet, key)
    supplied_id = required_text(packet, "delta_id")
    if supplied_id != expected_delta_id(packet):
        raise ValueError("source delta_id does not match deterministic delta payload identity")


def delta_observed_symptom(packet: Mapping[str, object]) -> str:
    claim_key = required_text(packet, "claim_key")
    current = packet.get("current_value")
    current_text = current.strip() if isinstance(current, str) and current.strip() else "<none>"
    observed = _string_sequence(packet, "observed_values", required=False)
    states = _string_sequence(packet, "cross_reference_states", required=True)
    triangulation = required_text(packet, "triangulation_state")
    action = required_text(packet, "recommended_action")
    observed_text = ", ".join(observed) if observed else "<none>"
    return (
        f"claim={claim_key}; current={current_text}; observed={observed_text}; "
        f"cross_reference={','.join(states)}; triangulation={triangulation}; "
        f"recommended_action={action}"
    )


def build_delta_reflection_candidate(packet: Mapping[str, object], request: Mapping[str, object]) -> DeltaReflectionCandidate:
    validate_delta_packet(packet)
    delta_id = required_text(packet, "delta_id")
    evidence_refs = _string_sequence(packet, "evidence_refs", required=True)
    digest = canonical_digest(packet)
    claim_key = required_text(packet, "claim_key")
    triangulation_state = required_text(packet, "triangulation_state")
    recommended_action = required_text(packet, "recommended_action")
    material = packet["material"]
    assert isinstance(material, bool)
    current_value = packet.get("current_claim_id")
    current_claim_id = current_value if isinstance(current_value, str) and current_value.strip() else None

    counts = {
        "independent_root_count": _required_int(packet, "independent_root_count"),
        "correlated_root_count": _required_int(packet, "correlated_root_count"),
        "reproduction_count": _required_int(packet, "reproduction_count"),
        "unknown_lineage_count": _required_int(packet, "unknown_lineage_count"),
    }
    core = build_reflection_core(
        source_kind="EVIDENCE_DELTA",
        source_id=delta_id,
        source_digest=digest,
        source_evidence_refs=evidence_refs,
        observed_symptom=delta_observed_symptom(packet),
        request=request,
        identity_context={
            "claim_key": claim_key,
            "current_claim_id": current_claim_id,
            "triangulation_state": triangulation_state,
            **counts,
            "material": material,
            "recommended_action": recommended_action,
            "observed_values": packet.get("observed_values", []),
            "cross_reference_states": packet.get("cross_reference_states", []),
        },
    )
    return DeltaReflectionCandidate(
        schema=DELTA_REFLECTION_SCHEMA,
        reflection_id=core.reflection_id,
        source_delta_id=delta_id,
        source_delta_digest=digest,
        claim_key=claim_key,
        current_claim_id=current_claim_id,
        triangulation_state=triangulation_state,
        source_evidence_refs=evidence_refs,
        source_material=material,
        source_recommended_action=recommended_action,
        branch_key=core.branch_key,
        observed_symptom=core.observed_symptom,
        expected_behavior=core.expected_behavior,
        mechanism_hypothesis=core.mechanism_hypothesis,
        evidence_for=core.evidence_for,
        evidence_against=core.evidence_against,
        alternative_explanations=core.alternative_explanations,
        predicted_consequence=core.predicted_consequence,
        required_disconfirmation_test=core.required_disconfirmation_test,
        proposed_scope=core.proposed_scope,
        authority_effect=core.authority_effect,
        promotion_state=core.promotion_state,
        **counts,
    )


def candidate_to_dict(candidate: DeltaReflectionCandidate) -> dict:
    return asdict(candidate)
