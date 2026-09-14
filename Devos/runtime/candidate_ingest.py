#!/usr/bin/env python3
"""Ingest provenance-bound candidate knowledge packs into the DevOS runtime DB."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys

try:
    from .build_knowledge_db import build
    from .db_runtime import connect_runtime
    from .evidence_store import persist_episode
    from .reflection_store import persist_reflection
    from .learning_store import admit_bundle
except ImportError:
    from build_knowledge_db import build
    from db_runtime import connect_runtime
    from evidence_store import persist_episode
    from reflection_store import persist_reflection
    from learning_store import admit_bundle

DEVOS_ROOT = Path(__file__).resolve().parents[1]
PACK_SCHEMA = "devos-candidate-ingestion-pack/v1"
EVALUATION_POLICY = "source-recognition-only/v1"


def _require_text(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def validate_pack(pack: dict) -> None:
    if not isinstance(pack, dict):
        raise ValueError("candidate ingestion pack must be a JSON object")
    if pack.get("schema") != PACK_SCHEMA:
        raise ValueError(f"unsupported candidate ingestion pack schema: {pack.get('schema')!r}")
    if pack.get("evaluation_policy") != EVALUATION_POLICY:
        raise ValueError(f"unsupported candidate ingestion evaluation policy: {pack.get('evaluation_policy')!r}")
    for key in ("pack_id", "branch_key", "observed_at"):
        _require_text(pack, key)
    entries = pack.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("candidate ingestion pack requires non-empty entries")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("candidate ingestion entries must be objects")
        entry_id = _require_text(entry, "entry_id")
        _require_text(entry, "claim_key")
        if entry_id in seen:
            raise ValueError(f"duplicate candidate ingestion entry_id: {entry_id}")
        seen.add(entry_id)
        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{entry_id}: sources must be a non-empty array")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError(f"{entry_id}: source entries must be objects")
            for key in ("root_id", "root_kind", "observation_question", "evidence_ref", "value"):
                _require_text(source, key)
        for key in ("reflection", "procedure", "capability", "experience"):
            if not isinstance(entry.get(key), dict):
                raise ValueError(f"{entry_id}: {key} must be an object")
        procedure = entry["procedure"]
        forbidden = {"branch_scope", "source_reflection_ids", "source_evidence_refs"}
        supplied = sorted(forbidden.intersection(procedure))
        if supplied:
            raise ValueError(
                f"{entry_id}: procedure may not supply lineage-controlled fields: "
                + ", ".join(supplied)
            )
        _require_text(entry["experience"], "memory_type")
        _require_text(entry["experience"], "statement")


def _episode(pack: dict, entry: dict) -> dict:
    claim_key = entry["claim_key"].strip()
    current_claims = []
    current = entry.get("current_claim")
    if current is not None:
        if not isinstance(current, dict):
            raise ValueError(f"{entry['entry_id']}: current_claim must be an object")
        current_claims.append(
            {
                "claim_id": _require_text(current, "claim_id"),
                "claim_key": claim_key,
                "value": _require_text(current, "value"),
                "lifecycle": str(current.get("lifecycle", "candidate")),
            }
        )
    roots = []
    findings = []
    for ordinal, source in enumerate(entry["sources"], 1):
        root_id = source["root_id"].strip()
        evidence_ref = source["evidence_ref"].strip()
        roots.append(
            {
                "root_id": root_id,
                "root_kind": source["root_kind"].strip(),
                "observation_question": source["observation_question"].strip(),
                "provenance_refs": [evidence_ref],
            }
        )
        findings.append(
            {
                "finding_id": f"finding:{pack['pack_id']}:{entry['entry_id']}:{ordinal}",
                "claim_key": claim_key,
                "value": source["value"].strip(),
                "evidence_ref": evidence_ref,
                "root_ids": [root_id],
                "lineage_state": str(source.get("lineage_state", "INDEPENDENT_ROOT")),
            }
        )
    return {
        "episode_id": f"episode:{pack['pack_id']}:{entry['entry_id']}",
        "branch_key": pack["branch_key"],
        "claim_key": claim_key,
        "observed_at": pack["observed_at"],
        "current_claims": current_claims,
        "roots": roots,
        "findings": findings,
    }


def _reflection_request(pack: dict, entry: dict) -> dict:
    reflection = deepcopy(entry["reflection"])
    evidence_refs = [source["evidence_ref"].strip() for source in entry["sources"]]
    reflection["branch_key"] = pack["branch_key"]
    reflection["evidence_for"] = evidence_refs
    reflection.setdefault("evidence_against", [])
    return reflection


def _recognition_evaluation(entry_id: str) -> dict:
    return {
        "results": [
            {"fixture_id": f"{entry_id}-t0-contract", "tier": "T0", "passed": True, "input_identity": f"contract:{entry_id}"},
            {"fixture_id": f"{entry_id}-t1-source", "tier": "T1", "passed": True, "input_identity": f"source:{entry_id}"},
            {"fixture_id": f"{entry_id}-t2-development", "tier": "T2", "passed": False, "input_identity": f"development:{entry_id}"},
            {"fixture_id": f"{entry_id}-t3-holdout", "tier": "T3", "passed": False, "input_identity": f"holdout:{entry_id}"},
        ]
    }


def _learning_bundle(pack: dict, entry: dict, reflection: dict) -> dict:
    procedure = deepcopy(entry["procedure"])
    procedure["branch_scope"] = pack["branch_key"]
    procedure["source_reflection_ids"] = [reflection["reflection_id"]]
    procedure["source_evidence_refs"] = list(reflection["source_evidence_refs"])
    return {
        "observed_at": pack["observed_at"],
        "procedure": procedure,
        "evaluation": _recognition_evaluation(entry["entry_id"]),
        "capability": deepcopy(entry["capability"]),
        "experience": deepcopy(entry["experience"]),
    }


def ingest_pack(connection: sqlite3.Connection, pack: dict) -> dict:
    validate_pack(pack)
    branch_key = pack["branch_key"].strip()
    if connection.execute(
        "SELECT 1 FROM branch_state WHERE branch_key=?", (branch_key,)
    ).fetchone() is None:
        raise ValueError(f"unknown branch_key: {branch_key}")

    results = []
    for entry in pack["entries"]:
        evidence = persist_episode(connection, _episode(pack, entry))
        reflected = persist_reflection(
            connection,
            evidence["delta"]["delta_id"],
            _reflection_request(pack, entry),
        )
        learned = admit_bundle(
            connection,
            _learning_bundle(pack, entry, reflected["reflection"]),
        )
        results.append(
            {
                "entry_id": entry["entry_id"],
                "episode_id": evidence["episode_id"],
                "delta_id": evidence["delta"]["delta_id"],
                "triangulation_state": evidence["triangulation_state"],
                "reflection_id": reflected["reflection"]["reflection_id"],
                "reflection_replayed": reflected["replayed"],
                "memory_id": learned["memory_id"],
                "procedure_id": learned["procedure_id"],
                "capability_id": learned["capability_id"],
                "capability_event_id": learned["capability_event_id"],
                "learning_replayed": learned["replayed"],
                "maturity_stage": learned["maturity_stage"],
                "validated_for_transfer": learned["validated_for_transfer"],
                "authority_effect": learned["authority_effect"],
                "promotion_state": learned["promotion_state"],
            }
        )
    return {
        "pack_id": pack["pack_id"],
        "branch_key": branch_key,
        "entries": results,
        "authority_effect": "NONE",
        "promotion_state": "CANDIDATE_ONLY",
    }


def _ensure_db(devos_root: Path, host_root: Path, db_path: Path) -> None:
    if not db_path.exists():
        build(devos_root, host_root, db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    devos_root = args.devos_root.resolve()
    host_root = (args.host_root or devos_root.parent).resolve()
    db_path = (args.db or (devos_root / "state" / "devos-knowledge.db")).resolve()
    try:
        pack = json.loads(args.pack.read_text(encoding="utf-8"))
        _ensure_db(devos_root, host_root, db_path)
        connection = connect_runtime(db_path)
        try:
            result = ingest_pack(connection, pack)
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
