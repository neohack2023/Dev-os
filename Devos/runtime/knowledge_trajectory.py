#!/usr/bin/env python3
"""First-class trajectory records for DevOS knowledge state changes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
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


def _assertions_for_record(connection: sqlite3.Connection, record: Mapping[str, object]) -> dict[str, dict[str, object]]:
    ids = [str(record["from_assertion_id"]), str(record["to_assertion_id"])]
    rows = connection.execute(
        "SELECT assertion_id,subject_id,claim_hash FROM knowledge_assertions WHERE assertion_id IN (?,?)",
        ids,
    ).fetchall()
    return {row["assertion_id"]: dict(row) for row in rows}


def _resolve_edge(connection: sqlite3.Connection, record: Mapping[str, object], edge_id: str | None) -> sqlite3.Row:
    if edge_id:
        row = connection.execute(
            "SELECT edge_id,subject_id,relation,from_assertion_id,to_assertion_id,rationale,created_at "
            "FROM knowledge_lineage_edges WHERE edge_id=?",
            (edge_id,),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT edge_id,subject_id,relation,from_assertion_id,to_assertion_id,rationale,created_at "
            "FROM knowledge_lineage_edges WHERE subject_id=? AND relation=? AND from_assertion_id=? AND to_assertion_id=?",
            (
                record["subject_id"],
                str(record["relation"]).upper(),
                record["from_assertion_id"],
                record["to_assertion_id"],
            ),
        ).fetchone()
    if row is None:
        raise ValueError("transition requires an existing matching lineage edge")
    return row


def persist_transition(
    connection: sqlite3.Connection,
    record: Mapping[str, object],
    *,
    edge_id: str | None = None,
) -> str:
    """Persist one transition after binding it to the exact lineage edge it explains."""
    assertions = _assertions_for_record(connection, record)
    edge = _resolve_edge(connection, record, edge_id)
    validate_transition(record, assertions=assertions, edge=dict(edge))

    refs = sorted(dict.fromkeys(str(item) for item in record["basis_refs"]))
    metadata = record.get("metadata") or {}
    values = (
        str(record["transition_id"]),
        edge["edge_id"],
        str(record["subject_id"]),
        str(record["relation"]).upper(),
        str(record["from_assertion_id"]),
        str(record["to_assertion_id"]),
        str(record["reason"]).strip(),
        _canonical_json(refs),
        record.get("trigger_ref"),
        record.get("decision_ref"),
        str(record["effective_at"]),
        str(record["recorded_at"]),
        _canonical_json(metadata),
    )
    existing = connection.execute(
        "SELECT transition_id,edge_id,subject_id,relation,from_assertion_id,to_assertion_id,reason,basis_refs_json,"
        "trigger_ref,decision_ref,effective_at,recorded_at,metadata_json FROM knowledge_state_transitions WHERE transition_id=?",
        (record["transition_id"],),
    ).fetchone()
    if existing:
        if tuple(existing) != values:
            raise ValueError("transition identifier collision")
        return str(record["transition_id"])

    edge_existing = connection.execute(
        "SELECT transition_id FROM knowledge_state_transitions WHERE edge_id=?",
        (edge["edge_id"],),
    ).fetchone()
    if edge_existing:
        raise ValueError("lineage edge already has a persisted transition")

    connection.execute(
        "INSERT INTO knowledge_state_transitions(transition_id,edge_id,subject_id,relation,from_assertion_id,to_assertion_id,"
        "reason,basis_refs_json,trigger_ref,decision_ref,effective_at,recorded_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        values,
    )
    return str(record["transition_id"])


def compact_trajectory(connection: sqlite3.Connection, *, subject_id: str, limit: int = 8) -> list[dict[str, object]]:
    if limit < 0:
        raise ValueError("trajectory limit must be non-negative")
    rows = connection.execute(
        "SELECT transition_id,edge_id,relation,from_assertion_id,to_assertion_id,reason,basis_refs_json,"
        "trigger_ref,decision_ref,effective_at,recorded_at FROM knowledge_state_transitions "
        "WHERE subject_id=? ORDER BY effective_at DESC, recorded_at DESC, transition_id DESC LIMIT ?",
        (subject_id, limit),
    ).fetchall()
    result: list[dict[str, object]] = []
    for row in reversed(rows):
        refs = json.loads(row["basis_refs_json"])
        result.append(
            {
                "transition_id": row["transition_id"],
                "edge_id": row["edge_id"],
                "relation": row["relation"],
                "from_assertion_id": row["from_assertion_id"],
                "to_assertion_id": row["to_assertion_id"],
                "reason": row["reason"],
                "basis_count": len(refs),
                "effective_at": row["effective_at"],
                "recorded_at": row["recorded_at"],
                "has_trigger": bool(row["trigger_ref"]),
                "has_decision": bool(row["decision_ref"]),
            }
        )
    return result


def expand_transition(connection: sqlite3.Connection, *, transition_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT transition_id,edge_id,subject_id,relation,from_assertion_id,to_assertion_id,reason,basis_refs_json,"
        "trigger_ref,decision_ref,effective_at,recorded_at,metadata_json FROM knowledge_state_transitions WHERE transition_id=?",
        (transition_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown transition_id: {transition_id}")
    return {
        "transition_id": row["transition_id"],
        "edge_id": row["edge_id"],
        "subject_id": row["subject_id"],
        "relation": row["relation"],
        "from_assertion_id": row["from_assertion_id"],
        "to_assertion_id": row["to_assertion_id"],
        "reason": row["reason"],
        "basis_refs": json.loads(row["basis_refs_json"]),
        "trigger_ref": row["trigger_ref"],
        "decision_ref": row["decision_ref"],
        "effective_at": row["effective_at"],
        "recorded_at": row["recorded_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def expand_trajectory(connection: sqlite3.Connection, *, subject_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT transition_id FROM knowledge_state_transitions WHERE subject_id=? "
        "ORDER BY effective_at,recorded_at,transition_id",
        (subject_id,),
    ).fetchall()
    return [expand_transition(connection, transition_id=row["transition_id"]) for row in rows]
