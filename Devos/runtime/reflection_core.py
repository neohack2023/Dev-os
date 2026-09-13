#!/usr/bin/env python3
"""Authority-neutral reflection hypothesis semantics for portable DevOS."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Mapping, Sequence

REFLECTION_CORE_SCHEMA = "devos-reflection-core/v1"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReflectionCore:
    schema: str
    reflection_id: str
    source_kind: str
    source_id: str
    source_digest: str
    source_evidence_refs: tuple[str, ...]
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


def required_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def string_list(mapping: Mapping[str, object], key: str, *, required: bool) -> tuple[str, ...]:
    value = mapping.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    items = tuple(sorted({item.strip() for item in value if item.strip()}))
    if required and not items:
        raise ValueError(f"{key} must contain at least one non-empty value")
    return items


def canonical_digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_reflection_core(
    *,
    source_kind: str,
    source_id: str,
    source_digest: str,
    source_evidence_refs: Sequence[str],
    observed_symptom: str,
    request: Mapping[str, object],
    identity_context: Mapping[str, object] | None = None,
) -> ReflectionCore:
    if not source_kind.strip():
        raise ValueError("source_kind must be non-empty")
    if not source_id.strip():
        raise ValueError("source_id must be non-empty")
    if not _SHA256_RE.fullmatch(source_digest):
        raise ValueError("source_digest must be sha256:<64 lowercase hex>")
    if not observed_symptom.strip():
        raise ValueError("observed_symptom must be non-empty")

    refs = tuple(sorted({ref.strip() for ref in source_evidence_refs if isinstance(ref, str) and ref.strip()}))
    if not refs:
        raise ValueError("source_evidence_refs must contain at least one reference")

    branch_key = required_text(request, "branch_key")
    expected_behavior = required_text(request, "expected_behavior")
    mechanism_hypothesis = required_text(request, "mechanism_hypothesis")
    evidence_for = string_list(request, "evidence_for", required=True)
    evidence_against = string_list(request, "evidence_against", required=False)
    alternatives = string_list(request, "alternative_explanations", required=True)
    predicted_consequence = required_text(request, "predicted_consequence")
    disconfirmation_test = required_text(request, "required_disconfirmation_test")
    proposed_scope = required_text(request, "proposed_scope")

    cited = set(evidence_for) | set(evidence_against)
    unknown = sorted(cited - set(refs))
    if unknown:
        raise ValueError("reflection evidence must be drawn from source_evidence_refs: " + ", ".join(unknown))
    normalized_hypothesis = " ".join(mechanism_hypothesis.casefold().split())
    if any(" ".join(item.casefold().split()) == normalized_hypothesis for item in alternatives):
        raise ValueError("alternative_explanations must differ from mechanism_hypothesis")

    payload = {
        "schema": REFLECTION_CORE_SCHEMA,
        "source_kind": source_kind.strip(),
        "source_id": source_id.strip(),
        "source_digest": source_digest,
        "source_evidence_refs": refs,
        "branch_key": branch_key,
        "observed_symptom": observed_symptom.strip(),
        "expected_behavior": expected_behavior,
        "mechanism_hypothesis": mechanism_hypothesis,
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "alternative_explanations": alternatives,
        "predicted_consequence": predicted_consequence,
        "required_disconfirmation_test": disconfirmation_test,
        "proposed_scope": proposed_scope,
        "authority_effect": "NONE",
        "promotion_state": "CANDIDATE_ONLY",
    }
    identity_payload = {"core": payload, "adapter_identity_context": dict(identity_context or {})}
    reflection_id = "reflection-" + canonical_digest(identity_payload).split(":", 1)[1][:16]
    return ReflectionCore(reflection_id=reflection_id, **payload)


def core_to_json(core: ReflectionCore) -> str:
    return json.dumps(asdict(core), indent=2, sort_keys=True) + "\n"
