#!/usr/bin/env python3
"""Deterministic stable-identity and lineage operations for DevOS knowledge."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

RELATIONS = {"CONFIRMS", "SUPERSEDES", "CONFLICTS"}
KINDS = {"episodic", "semantic", "procedural", "negative"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def subject_id(scope_key: str, knowledge_key: str) -> str:
    if not scope_key.strip() or not knowledge_key.strip():
        raise ValueError("scope_key and knowledge_key are required")
    return "ks_" + _sha256([scope_key, knowledge_key])[:24]


def ensure_subject(
    connection: sqlite3.Connection,
    *,
    scope_key: str,
    knowledge_key: str,
    knowledge_kind: str,
    created_at: str | None = None,
) -> str:
    if knowledge_kind not in KINDS:
        raise ValueError(f"unknown knowledge_kind: {knowledge_kind}")
    sid = subject_id(scope_key, knowledge_key)
    existing = connection.execute(
        "SELECT subject_id,knowledge_kind FROM knowledge_subjects WHERE scope_key=? AND knowledge_key=?",
        (scope_key, knowledge_key),
    ).fetchone()
    if existing:
        if existing["knowledge_kind"] != knowledge_kind:
            raise ValueError("stable knowledge identity cannot change knowledge_kind")
        return existing["subject_id"]
    connection.execute(
        "INSERT INTO knowledge_subjects(subject_id,scope_key,knowledge_key,knowledge_kind,created_at) VALUES (?,?,?,?,?)",
        (sid, scope_key, knowledge_key, knowledge_kind, created_at or _now()),
    )
    return sid


def append_assertion(
    connection: sqlite3.Connection,
    *,
    subject_id: str,
    claim: object,
    evidence_refs: list[str] | None = None,
    effective_at: str | None = None,
    recorded_at: str | None = None,
) -> str:
    subject = connection.execute(
        "SELECT subject_id FROM knowledge_subjects WHERE subject_id=?", (subject_id,)
    ).fetchone()
    if not subject:
        raise ValueError(f"unknown subject_id: {subject_id}")
    refs = sorted(dict.fromkeys(str(item) for item in (evidence_refs or [])))
    claim_hash = _sha256(claim)
    recorded = recorded_at or _now()
    aid = "ka_" + _sha256([subject_id, claim_hash, refs, effective_at, recorded])[:24]
    payload_json = _canonical_json(claim)
    refs_json = _canonical_json(refs)
    existing = connection.execute(
        "SELECT claim_hash,payload_json,evidence_refs_json,effective_at,recorded_at FROM knowledge_assertions WHERE assertion_id=?",
        (aid,),
    ).fetchone()
    if existing:
        expected = (claim_hash, payload_json, refs_json, effective_at, recorded)
        actual = tuple(existing)
        if actual != expected:
            raise ValueError("assertion identifier collision")
        return aid
    connection.execute(
        "INSERT INTO knowledge_assertions(assertion_id,subject_id,claim_hash,payload_json,evidence_refs_json,effective_at,recorded_at) VALUES (?,?,?,?,?,?,?)",
        (aid, subject_id, claim_hash, payload_json, refs_json, effective_at, recorded),
    )
    return aid


def _assertion(connection: sqlite3.Connection, assertion_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT assertion_id,subject_id,claim_hash FROM knowledge_assertions WHERE assertion_id=?",
        (assertion_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"unknown assertion_id: {assertion_id}")
    return row


def _would_create_supersedes_cycle(connection: sqlite3.Connection, newer: str, older: str) -> bool:
    # Edge direction is newer -> older. A cycle exists if older already reaches newer.
    row = connection.execute(
        "WITH RECURSIVE walk(id) AS ("
        " SELECT to_assertion_id FROM knowledge_lineage_edges WHERE relation='SUPERSEDES' AND from_assertion_id=?"
        " UNION"
        " SELECT e.to_assertion_id FROM knowledge_lineage_edges e JOIN walk w ON e.from_assertion_id=w.id WHERE e.relation='SUPERSEDES'"
        ") SELECT 1 FROM walk WHERE id=? LIMIT 1",
        (older, newer),
    ).fetchone()
    return row is not None


def link_assertions(
    connection: sqlite3.Connection,
    *,
    relation: str,
    from_assertion_id: str,
    to_assertion_id: str,
    rationale: str = "",
    created_at: str | None = None,
) -> str:
    relation = relation.upper()
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation: {relation}")
    if from_assertion_id == to_assertion_id:
        raise ValueError("lineage relation cannot self-link")
    source = _assertion(connection, from_assertion_id)
    target = _assertion(connection, to_assertion_id)
    if source["subject_id"] != target["subject_id"]:
        raise ValueError("lineage relations cannot cross stable knowledge identities")
    if relation == "CONFIRMS" and source["claim_hash"] != target["claim_hash"]:
        raise ValueError("CONFIRMS requires identical canonical claim content")
    if relation in {"SUPERSEDES", "CONFLICTS"} and source["claim_hash"] == target["claim_hash"]:
        raise ValueError(f"{relation} requires different canonical claim content")
    if relation == "SUPERSEDES" and _would_create_supersedes_cycle(connection, from_assertion_id, to_assertion_id):
        raise ValueError("SUPERSEDES would create a cycle")
    created = created_at or _now()
    edge_id = "ke_" + _sha256([relation, from_assertion_id, to_assertion_id])[:24]
    existing = connection.execute(
        "SELECT subject_id,relation,from_assertion_id,to_assertion_id,rationale FROM knowledge_lineage_edges WHERE edge_id=?",
        (edge_id,),
    ).fetchone()
    if existing:
        expected = (source["subject_id"], relation, from_assertion_id, to_assertion_id, rationale)
        if tuple(existing) != expected:
            raise ValueError("lineage edge identifier collision")
        return edge_id
    connection.execute(
        "INSERT INTO knowledge_lineage_edges(edge_id,subject_id,relation,from_assertion_id,to_assertion_id,rationale,created_at) VALUES (?,?,?,?,?,?,?)",
        (edge_id, source["subject_id"], relation, from_assertion_id, to_assertion_id, rationale, created),
    )
    return edge_id


def current_state(connection: sqlite3.Connection, *, subject_id: str) -> dict[str, object]:
    rows = connection.execute(
        "SELECT a.assertion_id,a.claim_hash,a.payload_json,a.evidence_refs_json,a.effective_at,a.recorded_at "
        "FROM knowledge_assertions a WHERE a.subject_id=? AND NOT EXISTS ("
        " SELECT 1 FROM knowledge_lineage_edges e WHERE e.relation='SUPERSEDES' AND e.to_assertion_id=a.assertion_id"
        ") ORDER BY a.recorded_at,a.assertion_id",
        (subject_id,),
    ).fetchall()
    if not rows:
        return {"subject_id": subject_id, "status": "EMPTY", "claims": []}
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["claim_hash"], []).append(row)
    claims = []
    for claim_hash, items in sorted(grouped.items()):
        claims.append(
            {
                "claim_hash": claim_hash,
                "assertion_ids": [item["assertion_id"] for item in items],
                "support_count": len(items),
                "claim": json.loads(items[-1]["payload_json"]),
                "effective_at": items[-1]["effective_at"],
                "recorded_at": items[-1]["recorded_at"],
            }
        )
    status = "ACTIVE" if len(claims) == 1 else "CONTESTED"
    return {"subject_id": subject_id, "status": status, "claims": claims}
