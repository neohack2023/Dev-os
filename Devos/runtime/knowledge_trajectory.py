#!/usr/bin/env python3
"""First-class trajectory records for DevOS knowledge state changes."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

RELATIONS = {"CONFIRMS", "SUPERSEDES", "CONFLICTS"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def transition_id(
    *,
    subject_id: str,
    relation: str,
    from_assertion_id: str,
    to_assertion_id: str,
    reason: str,
    basis_refs: list[str],
    effective_at: str,
    recorded_at: str,
) -> str:
    relation = relation.upper()
    refs = sorted(dict.fromkeys(str(item) for item in basis_refs))
    payload = [
        subject_id,
        relation,
        from_assertion_id,
        to_assertion_id,
        reason.strip(),
        refs,
        effective_at,
        recorded_at,
    ]
    return "kt_" + _sha256(payload)[:24]


def build_transition(
    *,
    subject_id: str,
    relation: str,
    from_assertion_id: str,
    to_assertion_id: str,
    reason: str,
    basis_refs: list[str],
    effective_at: str,
    recorded_at: str,
    trigger_ref: str | None = None,
    decision_ref: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    relation = relation.upper()
    refs = sorted(dict.fromkeys(str(item).strip() for item in basis_refs if str(item).strip()))
    record: dict[str, object] = {
        "subject_id": subject_id,
        "relation": relation,
        "from_assertion_id": from_assertion_id,
        "to_assertion_id": to_assertion_id,
        "reason": reason.strip(),
        "basis_refs": refs,
        "trigger_ref": trigger_ref,
        "decision_ref": decision_ref,
        "effective_at": effective_at,
        "recorded_at": recorded_at,
        "metadata": metadata or {},
    }
    record["transition_id"] = transition_id(
        subject_id=subject_id,
        relation=relation,
        from_assertion_id=from_assertion_id,
        to_assertion_id=to_assertion_id,
        reason=record["reason"],
        basis_refs=refs,
        effective_at=effective_at,
        recorded_at=recorded_at,
    )
    validate_transition(record)
    return record


def validate_transition(
    record: Mapping[str, object],
    *,
    assertions: Mapping[str, Mapping[str, object]] | None = None,
    edge: Mapping[str, object] | None = None,
) -> None:
    required = {
        "transition_id",
        "subject_id",
        "relation",
        "from_assertion_id",
        "to_assertion_id",
        "reason",
        "basis_refs",
        "effective_at",
        "recorded_at",
    }
    missing = sorted(key for key in required if not record.get(key))
    if missing:
        raise ValueError(f"transition missing required fields: {', '.join(missing)}")

    relation = str(record["relation"]).upper()
    if relation not in RELATIONS:
        raise ValueError(f"unknown transition relation: {relation}")
    if record["from_assertion_id"] == record["to_assertion_id"]:
        raise ValueError("transition cannot self-link")
    if not str(record["reason"]).strip():
        raise ValueError("transition reason is required")

    refs = record["basis_refs"]
    if not isinstance(refs, list) or not refs or any(not str(item).strip() for item in refs):
        raise ValueError("transition basis_refs must contain at least one non-empty evidence reference")
    if len({str(item) for item in refs}) != len(refs):
        raise ValueError("transition basis_refs must be unique")

    expected_id = transition_id(
        subject_id=str(record["subject_id"]),
        relation=relation,
        from_assertion_id=str(record["from_assertion_id"]),
        to_assertion_id=str(record["to_assertion_id"]),
        reason=str(record["reason"]),
        basis_refs=[str(item) for item in refs],
        effective_at=str(record["effective_at"]),
        recorded_at=str(record["recorded_at"]),
    )
    if record["transition_id"] != expected_id:
        raise ValueError("transition_id does not match canonical transition content")

    if assertions is not None:
        source = assertions.get(str(record["from_assertion_id"]))
        target = assertions.get(str(record["to_assertion_id"]))
        if source is None or target is None:
            raise ValueError("transition references unknown assertion")
        if source.get("subject_id") != record["subject_id"] or target.get("subject_id") != record["subject_id"]:
            raise ValueError("transition assertions must share the transition subject_id")
        source_hash = source.get("claim_hash")
        target_hash = target.get("claim_hash")
        if relation == "CONFIRMS" and source_hash != target_hash:
            raise ValueError("CONFIRMS transition requires identical claim hashes")
        if relation in {"SUPERSEDES", "CONFLICTS"} and source_hash == target_hash:
            raise ValueError(f"{relation} transition requires different claim hashes")

    if edge is not None:
        for key in ("subject_id", "relation", "from_assertion_id", "to_assertion_id"):
            left = str(record[key]).upper() if key == "relation" else record[key]
            right = str(edge.get(key)).upper() if key == "relation" else edge.get(key)
            if left != right:
                raise ValueError(f"transition does not match lineage edge field: {key}")


def trajectory(records: list[Mapping[str, object]], *, subject_id: str) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in records:
        validate_transition(item)
        if item["subject_id"] != subject_id:
            continue
        tid = str(item["transition_id"])
        if tid in seen:
            raise ValueError(f"duplicate transition_id: {tid}")
        seen.add(tid)
        selected.append(dict(item))
    return sorted(selected, key=lambda row: (str(row["effective_at"]), str(row["recorded_at"]), str(row["transition_id"])))
