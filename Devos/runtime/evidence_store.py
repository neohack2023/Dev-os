#!/usr/bin/env python3
"""Admit immutable evidence episodes into the portable DevOS runtime database."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

try:
    from .build_knowledge_db import build
    from .db_runtime import connect_runtime
    from .evidence_runtime import AtomicFinding, CurrentClaim, LineageState, build_delta_packet, cross_reference, triangulate
except ImportError:
    from build_knowledge_db import build
    from db_runtime import connect_runtime
    from evidence_runtime import AtomicFinding, CurrentClaim, LineageState, build_delta_packet, cross_reference, triangulate

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = DEVOS_ROOT / "state" / "devos-knowledge.db"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _id(prefix: str, payload: object) -> str:
    return prefix + _digest(payload)[:16]


def _require_string(row: dict, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing non-empty string: {key}")
    return value


def validate_episode(episode: dict) -> None:
    if not isinstance(episode, dict):
        raise ValueError("episode must be a JSON object")
    for key in ("episode_id", "branch_key", "claim_key", "observed_at"):
        _require_string(episode, key)
    roots = episode.get("roots")
    findings = episode.get("findings")
    claims = episode.get("current_claims", [])
    if not isinstance(roots, list) or not isinstance(findings, list) or not isinstance(claims, list):
        raise ValueError("roots, findings, and current_claims must be arrays")
    if not findings:
        raise ValueError("episode must contain at least one finding")
    root_ids: set[str] = set()
    for root in roots:
        if not isinstance(root, dict):
            raise ValueError("root entries must be objects")
        root_id = _require_string(root, "root_id")
        if root_id in root_ids:
            raise ValueError(f"duplicate root_id in episode: {root_id}")
        root_ids.add(root_id)
        _require_string(root, "root_kind")
        _require_string(root, "observation_question")
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("finding entries must be objects")
        finding_id = _require_string(finding, "finding_id")
        if finding_id in finding_ids:
            raise ValueError(f"duplicate finding_id in episode: {finding_id}")
        finding_ids.add(finding_id)
        _require_string(finding, "claim_key")
        _require_string(finding, "value")
        _require_string(finding, "evidence_ref")
        LineageState(finding.get("lineage_state", "UNKNOWN_LINEAGE"))
        refs = finding.get("root_ids", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ValueError(f"{finding_id}: root_ids must be non-empty strings")
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("current_claim entries must be objects")
        for key in ("claim_id", "claim_key", "value"):
            _require_string(claim, key)


def _claims(rows: list[dict]) -> dict[str, CurrentClaim]:
    claims: dict[str, CurrentClaim] = {}
    for row in rows:
        claim = CurrentClaim(
            claim_id=row["claim_id"],
            claim_key=row["claim_key"],
            value=row["value"],
            lifecycle=row.get("lifecycle", "active"),
        )
        if claim.claim_key in claims:
            raise ValueError(f"duplicate current claim key: {claim.claim_key}")
        claims[claim.claim_key] = claim
    return claims


def _finding(row: dict) -> AtomicFinding:
    return AtomicFinding(
        finding_id=row["finding_id"],
        claim_key=row["claim_key"],
        value=row["value"],
        evidence_ref=row["evidence_ref"],
        root_ids=tuple(row.get("root_ids", [])),
        lineage_state=LineageState(row.get("lineage_state", "UNKNOWN_LINEAGE")),
        shared_input_keys=tuple(row.get("shared_input_keys", [])),
        related_claim_keys=tuple(row.get("related_claim_keys", [])),
        supersedes_claim_id=row.get("supersedes_claim_id"),
    )


def _immutable_insert(connection: sqlite3.Connection, table: str, id_column: str, identifier: str, values: dict) -> None:
    existing = connection.execute(f"SELECT * FROM {table} WHERE {id_column}=?", (identifier,)).fetchone()
    if existing is not None:
        for key, expected in values.items():
            if existing[key] != expected:
                raise ValueError(f"immutable evidence conflict: {table}.{identifier} differs at {key}")
        return
    columns = [id_column, *values.keys()]
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table}({','.join(columns)}) VALUES ({placeholders})",
        [identifier, *values.values()],
    )


def persist_episode(connection: sqlite3.Connection, episode: dict) -> dict:
    validate_episode(episode)
    branch_key = episode["branch_key"]
    if connection.execute("SELECT 1 FROM branch_state WHERE branch_key=?", (branch_key,)).fetchone() is None:
        raise ValueError(f"unknown branch_key: {branch_key}")
    observed_at = episode["observed_at"]
    claims = _claims(episode.get("current_claims", []))
    findings = [_finding(row) for row in episode["findings"]]
    known_roots = {
        row[0]
        for row in connection.execute("SELECT root_id FROM evidence_roots").fetchall()
    }
    incoming_roots = {root["root_id"] for root in episode.get("roots", [])}
    for finding in findings:
        missing = sorted(set(finding.root_ids) - known_roots - incoming_roots)
        if missing:
            raise ValueError(f"{finding.finding_id}: unknown root ids: {', '.join(missing)}")

    try:
        connection.execute("BEGIN IMMEDIATE")
        for root in episode.get("roots", []):
            root_payload = {
                "root_kind": root["root_kind"],
                "observation_question": root["observation_question"],
                "input_identity": root.get("input_identity", ""),
                "execution_identity": root.get("execution_identity", ""),
                "source_revision": root.get("source_revision", ""),
                "environment_identity": root.get("environment_identity", ""),
                "provenance_json": json.dumps(root.get("provenance_refs", []), sort_keys=True),
                "created_at": observed_at,
                "row_hash": _digest(root),
            }
            _immutable_insert(connection, "evidence_roots", "root_id", root["root_id"], root_payload)

        assessments = []
        for finding in findings:
            finding_row = next(row for row in episode["findings"] if row["finding_id"] == finding.finding_id)
            finding_payload = {
                "episode_id": episode["episode_id"],
                "branch_key": branch_key,
                "claim_key": finding.claim_key,
                "value_text": finding.value,
                "evidence_ref": finding.evidence_ref,
                "root_ids_json": json.dumps(finding.root_ids),
                "lineage_state": finding.lineage_state.value,
                "shared_input_keys_json": json.dumps(finding.shared_input_keys),
                "related_claim_keys_json": json.dumps(finding.related_claim_keys),
                "supersedes_claim_id": finding.supersedes_claim_id,
                "created_at": observed_at,
                "row_hash": _digest(finding_row),
            }
            _immutable_insert(connection, "atomic_findings", "finding_id", finding.finding_id, finding_payload)
            for ordinal, root_id in enumerate(finding.root_ids):
                connection.execute(
                    "INSERT OR IGNORE INTO finding_roots(finding_id,root_id,ordinal) VALUES (?,?,?)",
                    (finding.finding_id, root_id, ordinal),
                )
            assessment = cross_reference(finding, claims)
            assessments.append(assessment)
            assessment_payload = {
                "finding_id": finding.finding_id,
                "cross_reference": assessment.cross_reference.value,
                "current_claim_id": assessment.current_claim_id,
                "created_at": observed_at,
            }
            assessment_id = _id("assessment-", assessment_payload)
            _immutable_insert(connection, "finding_assessments", "assessment_id", assessment_id, assessment_payload)

        tri = triangulate(assessments, claim_key=episode["claim_key"])
        tri_payload = {
            "claim_key": tri.claim_key,
            "state": tri.state.value,
            "root_summary_json": json.dumps(asdict(tri.root_summary), sort_keys=True),
            "supporting_root_ids_json": json.dumps(tri.supporting_root_ids),
            "contradicting_root_ids_json": json.dumps(tri.contradicting_root_ids),
            "notes_json": json.dumps(tri.notes),
            "created_at": observed_at,
        }
        batch_id = _id("tri-", {"episode_id": episode["episode_id"], **tri_payload})
        _immutable_insert(connection, "triangulation_batches", "batch_id", batch_id, tri_payload)

        delta = build_delta_packet(assessments, tri, claims)
        delta_payload = {
            "claim_key": delta.claim_key,
            "payload_json": json.dumps(asdict(delta), sort_keys=True),
            "created_at": observed_at,
        }
        _immutable_insert(connection, "evidence_delta_packets", "delta_id", delta.delta_id, delta_payload)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return {
        "episode_id": episode["episode_id"],
        "branch_key": branch_key,
        "batch_id": batch_id,
        "triangulation_state": tri.state.value,
        "delta": asdict(delta),
        "authority_effect": "NONE",
    }


def list_evidence(connection: sqlite3.Connection, branch_key: str | None = None) -> dict:
    where = " WHERE branch_key=?" if branch_key else ""
    args = (branch_key,) if branch_key else ()
    findings = [dict(row) for row in connection.execute(
        "SELECT finding_id,episode_id,branch_key,claim_key,value_text,evidence_ref,lineage_state,created_at FROM atomic_findings" + where + " ORDER BY created_at,finding_id",
        args,
    ).fetchall()]
    return {
        "roots": connection.execute("SELECT count(*) FROM evidence_roots").fetchone()[0],
        "findings": findings,
        "deltas": [dict(row) for row in connection.execute("SELECT delta_id,claim_key,payload_json,created_at FROM evidence_delta_packets ORDER BY created_at,delta_id").fetchall()],
    }


def _ensure_db(devos_root: Path, host_root: Path, db_path: Path) -> None:
    if not db_path.exists():
        build(devos_root, host_root, db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--db", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    p_admit = sub.add_parser("admit")
    p_admit.add_argument("input", type=Path)
    p_list = sub.add_parser("list")
    p_list.add_argument("--branch")
    args = parser.parse_args()
    devos_root = args.devos_root.resolve()
    host_root = (args.host_root or devos_root.parent).resolve()
    db_path = (args.db or (devos_root / "state" / "devos-knowledge.db")).resolve()
    try:
        _ensure_db(devos_root, host_root, db_path)
        connection = connect_runtime(db_path)
        try:
            if args.command == "admit":
                episode = json.loads(args.input.read_text(encoding="utf-8"))
                result = persist_episode(connection, episode)
            else:
                result = list_evidence(connection, args.branch)
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
