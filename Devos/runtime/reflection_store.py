#!/usr/bin/env python3
"""Persist immutable, authority-neutral reflection candidates derived from admitted evidence deltas."""
from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

try:
    from .db_runtime import connect_runtime
    from .delta_reflection import build_delta_reflection_candidate
except ImportError:
    from db_runtime import connect_runtime
    from delta_reflection import build_delta_reflection_candidate

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = DEVOS_ROOT / "state" / "devos-knowledge.db"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_delta(connection: sqlite3.Connection, delta_id: str) -> tuple[dict, str]:
    row = connection.execute(
        "SELECT payload_json, created_at FROM evidence_delta_packets WHERE delta_id=?",
        (delta_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown delta_id: {delta_id}")
    payload = json.loads(row["payload_json"])
    if not isinstance(payload, dict):
        raise ValueError(f"delta payload is not an object: {delta_id}")
    return payload, row["created_at"]


def persist_reflection(connection: sqlite3.Connection, delta_id: str, request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("reflection request must be a JSON object")
    packet, source_created_at = load_delta(connection, delta_id)
    candidate = build_delta_reflection_candidate(packet, request)

    if connection.execute(
        "SELECT 1 FROM branch_state WHERE branch_key=?",
        (candidate.branch_key,),
    ).fetchone() is None:
        raise ValueError(f"unknown branch_key: {candidate.branch_key}")

    payload = asdict(candidate)
    payload_json = json.dumps(payload, sort_keys=True)
    row_hash = _digest(payload)
    values = {
        "source_kind": "EVIDENCE_DELTA",
        "source_id": candidate.source_delta_id,
        "source_digest": candidate.source_delta_digest,
        "branch_key": candidate.branch_key,
        "claim_key": candidate.claim_key,
        "mechanism_hypothesis": candidate.mechanism_hypothesis,
        "required_disconfirmation_test": candidate.required_disconfirmation_test,
        "authority_effect": candidate.authority_effect,
        "promotion_state": candidate.promotion_state,
        "payload_json": payload_json,
        "created_at": source_created_at,
        "row_hash": row_hash,
    }

    existing = connection.execute(
        "SELECT * FROM reflection_candidates WHERE reflection_id=?",
        (candidate.reflection_id,),
    ).fetchone()
    if existing is not None:
        for key, expected in values.items():
            if existing[key] != expected:
                raise ValueError(
                    f"immutable reflection conflict: {candidate.reflection_id} differs at {key}"
                )
        return {"reflection": payload, "replayed": True}

    columns = ["reflection_id", *values.keys()]
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO reflection_candidates({','.join(columns)}) VALUES ({placeholders})",
        [candidate.reflection_id, *values.values()],
    )
    connection.commit()
    return {"reflection": payload, "replayed": False}


def list_reflections(connection: sqlite3.Connection, branch_key: str | None = None) -> list[dict]:
    where = " WHERE branch_key=?" if branch_key else ""
    args = (branch_key,) if branch_key else ()
    rows = connection.execute(
        "SELECT reflection_id,source_kind,source_id,branch_key,claim_key,"
        "mechanism_hypothesis,required_disconfirmation_test,authority_effect,"
        "promotion_state,created_at FROM reflection_candidates"
        + where
        + " ORDER BY created_at,reflection_id",
        args,
    ).fetchall()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    p_reflect = sub.add_parser("reflect")
    p_reflect.add_argument("--delta", required=True)
    p_reflect.add_argument("--request", type=Path, required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--branch")
    args = parser.parse_args()

    try:
        connection = connect_runtime(args.db.resolve())
        try:
            if args.command == "reflect":
                request = json.loads(args.request.read_text(encoding="utf-8"))
                result = persist_reflection(connection, args.delta, request)
            else:
                result = {"reflections": list_reflections(connection, args.branch)}
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
