#!/usr/bin/env python3
"""Governed DevOS promotion gate: learning -> locked STONE envelope -> MASON handoff decision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys

try:
    from .db_runtime import connect_runtime
except ImportError:
    from db_runtime import connect_runtime

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = DEVOS_ROOT / "state" / "devos-knowledge.db"
AUTHORITY_EFFECT = "NONE"
PROMOTION_STATE = "CANDIDATE_ONLY"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSFER_OR_HIGHER = {"TRANSFER", "COMPOSITION", "ADAPTATION", "METACOGNITIVE_CONTROL"}
_OUTCOMES = {"PROMOTE", "REVISE", "ROLLBACK", "NO_OP"}


def _canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}:" + hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()[:24]


def _required_text(mapping: dict, key: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _project_repository(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT value FROM project_meta WHERE key='repository'").fetchone()
    return str(row[0]) if row is not None else ""


def _load_learning_context(connection: sqlite3.Connection, capability_id: str) -> dict:
    row = connection.execute(
        "SELECT payload_json FROM learning_capabilities WHERE capability_id=?", (capability_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown capability_id: {capability_id}")
    capability = json.loads(row["payload_json"])
    maturity = str(capability.get("maturity_stage", ""))
    if maturity not in _TRANSFER_OR_HIGHER:
        raise ValueError("capability has not reached held-out transfer maturity")
    branch_scope = _required_text(capability, "branch_scope")
    if connection.execute("SELECT 1 FROM branch_state WHERE branch_key=?", (branch_scope,)).fetchone() is None:
        raise ValueError(f"unknown branch scope for capability: {branch_scope}")

    event = connection.execute(
        "SELECT event_id,payload_json FROM learning_capability_events "
        "WHERE capability_id=? ORDER BY event_sequence DESC LIMIT 1",
        (capability_id,),
    ).fetchone()
    if event is None:
        raise ValueError("capability has no lifecycle event")
    event_payload = json.loads(event["payload_json"])
    evaluation_id = _required_text(event_payload, "evaluation_id")
    evaluation_row = connection.execute(
        "SELECT payload_json FROM learning_evaluations WHERE evaluation_id=?", (evaluation_id,)
    ).fetchone()
    if evaluation_row is None:
        raise ValueError(f"missing learning evaluation: {evaluation_id}")
    evaluation = json.loads(evaluation_row["payload_json"])
    if not bool(evaluation.get("validated_for_transfer")):
        raise ValueError("promotion requires held-out transfer validation")
    if not bool(evaluation.get("regression_safe")):
        raise ValueError("promotion requires regression-safe evaluation")

    procedure_edge = connection.execute(
        "SELECT procedure_id FROM evaluation_procedures WHERE evaluation_id=?", (evaluation_id,)
    ).fetchone()
    if procedure_edge is None:
        raise ValueError("evaluation is not bound to a learning procedure")
    procedure_id = str(procedure_edge["procedure_id"])
    procedure_row = connection.execute(
        "SELECT payload_json FROM learning_procedures WHERE procedure_id=?", (procedure_id,)
    ).fetchone()
    if procedure_row is None:
        raise ValueError(f"missing learning procedure: {procedure_id}")
    procedure = json.loads(procedure_row["payload_json"])

    reflection_rows = connection.execute(
        "SELECT reflection_id FROM procedure_reflections WHERE procedure_id=? ORDER BY reflection_id",
        (procedure_id,),
    ).fetchall()
    reflection_ids = [str(item["reflection_id"]) for item in reflection_rows]
    if not reflection_ids:
        raise ValueError("promotion requires reflection lineage")
    evidence_refs: set[str] = set()
    for reflection_id in reflection_ids:
        reflection = connection.execute(
            "SELECT payload_json FROM reflection_candidates WHERE reflection_id=?", (reflection_id,)
        ).fetchone()
        if reflection is None:
            raise ValueError(f"missing reflection lineage: {reflection_id}")
        payload = json.loads(reflection["payload_json"])
        evidence_refs.update(str(ref).strip() for ref in payload.get("source_evidence_refs", []) if str(ref).strip())
    if not evidence_refs:
        raise ValueError("promotion lineage contains no evidence references")

    return {
        "capability_id": capability_id,
        "capability_event_id": str(event["event_id"]),
        "maturity_stage": maturity,
        "branch_scope": branch_scope,
        "evaluation_id": evaluation_id,
        "procedure_id": procedure_id,
        "reflection_ids": reflection_ids,
        "evidence_refs": sorted(evidence_refs),
        "transfer_validated": True,
        "regression_safe": True,
        "learning_canary_validated": bool(evaluation.get("canary_validated")),
    }


def _normalize_paths(paths: object) -> list[str]:
    if not isinstance(paths, list) or not paths:
        raise ValueError("target.paths must be a non-empty list")
    normalized: set[str] = set()
    for raw in paths:
        value = str(raw).strip().replace("\\", "/")
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe target path: {value!r}")
        normalized.add(str(path))
    return sorted(normalized)


def _normalize_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("verification_plan must be an object")
    raw_checks = plan.get("required_checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ValueError("verification_plan.required_checks must be non-empty")
    checks: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_checks:
        if not isinstance(item, dict):
            raise ValueError("required check entries must be objects")
        name = _required_text(item, "name")
        source = _required_text(item, "source")
        key = (name, source)
        if key in seen:
            raise ValueError(f"duplicate required check: {name} from {source}")
        seen.add(key)
        checks.append({"name": name, "source": source})
    checks.sort(key=lambda item: (item["name"], item["source"]))
    require_review = bool(plan.get("require_independent_review", False))
    review_source = str(plan.get("review_source", "")).strip()
    if require_review and not review_source:
        raise ValueError("review_source is required when independent review is required")
    require_canary = bool(plan.get("require_canary", False))
    canary_source = str(plan.get("canary_source", "")).strip()
    if require_canary and not canary_source:
        raise ValueError("canary_source is required when canary verification is required")
    return {
        "required_checks": checks,
        "require_independent_review": require_review,
        "review_source": review_source,
        "require_canary": require_canary,
        "canary_source": canary_source,
    }


def build_envelope(connection: sqlite3.Connection, request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("promotion request must be a JSON object")
    observed_at = _required_text(request, "observed_at")
    capability_id = _required_text(request, "capability_id")
    candidate_revision = _required_text(request, "candidate_revision")
    if not _SHA40.fullmatch(candidate_revision):
        raise ValueError("candidate_revision must be a 40-character lowercase Git SHA")
    change_digest = _required_text(request, "change_digest")
    if not _SHA256.fullmatch(change_digest):
        raise ValueError("change_digest must be a lowercase SHA-256 hex digest")
    if request.get("destination_authority") != "repository":
        raise ValueError("destination_authority must be repository")

    target = request.get("target")
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    repository = _required_text(target, "repository")
    projected_repository = _project_repository(connection)
    if projected_repository and repository != projected_repository:
        raise ValueError(f"target repository mismatch: {repository} != {projected_repository}")
    target_payload = {
        "repository": repository,
        "branch": _required_text(target, "branch"),
        "paths": _normalize_paths(target.get("paths")),
        "change_ref": _required_text(target, "change_ref"),
    }
    learning = _load_learning_context(connection, capability_id)
    verification_plan = _normalize_plan(request.get("verification_plan"))

    payload = {
        "schema_version": 1,
        "observed_at": observed_at,
        "source_learning": learning,
        "candidate_revision": candidate_revision,
        "change_digest": change_digest,
        "target": target_payload,
        "expected_benefit": _required_text(request, "expected_benefit"),
        "regression_risk": _required_text(request, "regression_risk"),
        "falsification_test": _required_text(request, "falsification_test"),
        "rollback_plan": _required_text(request, "rollback_plan"),
        "verification_plan": verification_plan,
        "required_authorization": _required_text(request, "required_authorization"),
        "destination_authority": "repository",
        "stone_state": "LOCKED",
        "mason_state": "HANDOFF_REQUIRED",
        "authority_effect": AUTHORITY_EFFECT,
        "promotion_state": PROMOTION_STATE,
        "write_authorized": False,
    }
    payload["envelope_id"] = _stable_id("promotion-envelope", payload)
    return payload


def persist_envelope(connection: sqlite3.Connection, request: dict) -> dict:
    envelope = build_envelope(connection, request)
    encoded = _canon(envelope)
    existing = connection.execute(
        "SELECT payload_json FROM promotion_envelopes WHERE envelope_id=?", (envelope["envelope_id"],)
    ).fetchone()
    if existing is not None:
        if existing["payload_json"] != encoded:
            raise ValueError(f"immutable promotion envelope conflict: {envelope['envelope_id']}")
        return {"envelope": envelope, "replayed": True}
    connection.execute(
        "INSERT INTO promotion_envelopes(envelope_id,capability_id,branch_scope,candidate_revision,"
        "change_digest,stone_state,mason_state,payload_json,observed_at,authority_effect,write_authorized) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,0)",
        (
            envelope["envelope_id"],
            envelope["source_learning"]["capability_id"],
            envelope["source_learning"]["branch_scope"],
            envelope["candidate_revision"],
            envelope["change_digest"],
            envelope["stone_state"],
            envelope["mason_state"],
            encoded,
            envelope["observed_at"],
            AUTHORITY_EFFECT,
        ),
    )
    connection.commit()
    return {"envelope": envelope, "replayed": False}


def _assert_revision(value: object, expected: str, label: str) -> None:
    if str(value or "").strip() != expected:
        raise ValueError(f"{label} is not bound to candidate revision {expected}")


def derive_decision(envelope: dict, verification: dict) -> dict:
    if not isinstance(verification, dict):
        raise ValueError("promotion verification must be a JSON object")
    observed_at = _required_text(verification, "observed_at")
    candidate_revision = envelope["candidate_revision"]
    _assert_revision(verification.get("candidate_revision"), candidate_revision, "verification")
    plan = envelope["verification_plan"]

    checks = verification.get("checks", [])
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    check_map: dict[tuple[str, str], dict] = {}
    for item in checks:
        if not isinstance(item, dict):
            raise ValueError("check entries must be objects")
        _assert_revision(item.get("revision"), candidate_revision, "status check")
        key = (_required_text(item, "name"), _required_text(item, "source"))
        if key in check_map:
            raise ValueError(f"duplicate verification check: {key[0]} from {key[1]}")
        check_map[key] = item

    reasons: list[str] = []
    for required in plan["required_checks"]:
        key = (required["name"], required["source"])
        actual = check_map.get(key)
        if actual is None:
            reasons.append(f"missing required check: {key[0]} from {key[1]}")
        elif str(actual.get("status", "")).lower() != "success":
            reasons.append(f"required check not successful: {key[0]} from {key[1]}")

    review = verification.get("review")
    if review is not None:
        if not isinstance(review, dict):
            raise ValueError("review must be an object")
        _assert_revision(review.get("revision"), candidate_revision, "review")
    if plan["require_independent_review"]:
        if not isinstance(review, dict):
            reasons.append("independent review missing")
        else:
            if str(review.get("source", "")).strip() != plan["review_source"]:
                reasons.append("independent review source mismatch")
            if str(review.get("status", "")).lower() != "approved":
                reasons.append("independent review is not approved")
            if bool(review.get("self_review", True)):
                reasons.append("self review cannot satisfy independent review")

    canary = verification.get("canary")
    if canary is not None:
        if not isinstance(canary, dict):
            raise ValueError("canary must be an object")
        _assert_revision(canary.get("revision"), candidate_revision, "canary")
    if plan["require_canary"]:
        if not isinstance(canary, dict):
            reasons.append("required canary missing")
        else:
            if str(canary.get("source", "")).strip() != plan["canary_source"]:
                reasons.append("canary source mismatch")
            if str(canary.get("status", "")).lower() != "success":
                reasons.append("required canary is not successful")

    rollback = verification.get("rollback")
    if not isinstance(rollback, dict):
        rollback = {}
    rollback_ready = bool(rollback.get("ready", False))
    rollback_triggered = bool(rollback.get("triggered", False))
    rollback_verified = bool(rollback.get("verified", False))
    no_op_reason = str(verification.get("no_op_reason", "")).strip()

    if rollback_triggered:
        outcome = "ROLLBACK" if rollback_verified else "REVISE"
        if not rollback_verified:
            reasons.append("rollback triggered but not verified")
    elif no_op_reason:
        outcome = "NO_OP"
    else:
        if not rollback_ready:
            reasons.append("rollback readiness is not verified")
        outcome = "PROMOTE" if not reasons else "REVISE"

    if outcome not in _OUTCOMES:
        raise AssertionError(outcome)
    next_action = {
        "PROMOTE": "MASON_REVIEW_PROMOTION",
        "REVISE": "REVISE_CANDIDATE",
        "ROLLBACK": "MASON_REVIEW_ROLLBACK",
        "NO_OP": "CLOSE_NO_OP",
    }[outcome]
    decision = {
        "schema_version": 1,
        "envelope_id": envelope["envelope_id"],
        "observed_at": observed_at,
        "candidate_revision": candidate_revision,
        "verification": verification,
        "outcome": outcome,
        "reasons": sorted(set(reasons)),
        "next_action": next_action,
        "mason_handoff_required": outcome in {"PROMOTE", "ROLLBACK"},
        "authority_effect": AUTHORITY_EFFECT,
        "promotion_state": PROMOTION_STATE,
        "write_authorized": False,
    }
    decision["decision_id"] = _stable_id("promotion-decision", decision)
    return decision


def persist_decision(connection: sqlite3.Connection, envelope_id: str, verification: dict) -> dict:
    row = connection.execute(
        "SELECT payload_json FROM promotion_envelopes WHERE envelope_id=?", (envelope_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown envelope_id: {envelope_id}")
    envelope = json.loads(row["payload_json"])
    decision = derive_decision(envelope, verification)
    encoded = _canon(decision)
    verifier_digest = hashlib.sha256(_canon(verification).encode("utf-8")).hexdigest()
    existing = connection.execute(
        "SELECT payload_json FROM promotion_decisions WHERE decision_id=?", (decision["decision_id"],)
    ).fetchone()
    if existing is not None:
        if existing["payload_json"] != encoded:
            raise ValueError(f"immutable promotion decision conflict: {decision['decision_id']}")
        return {"decision": decision, "replayed": True}
    connection.execute(
        "INSERT INTO promotion_decisions(decision_id,envelope_id,outcome,candidate_revision,verifier_digest,"
        "payload_json,observed_at,authority_effect,write_authorized) VALUES (?,?,?,?,?,?,?,?,0)",
        (
            decision["decision_id"],
            envelope_id,
            decision["outcome"],
            decision["candidate_revision"],
            verifier_digest,
            encoded,
            decision["observed_at"],
            AUTHORITY_EFFECT,
        ),
    )
    connection.commit()
    return {"decision": decision, "replayed": False}


def list_promotions(connection: sqlite3.Connection, branch: str | None = None) -> dict:
    where = " WHERE branch_scope=?" if branch else ""
    params = (branch,) if branch else ()
    envelopes = [dict(row) for row in connection.execute(
        "SELECT envelope_id,capability_id,branch_scope,candidate_revision,change_digest,stone_state,mason_state,"
        "observed_at,authority_effect,write_authorized FROM promotion_envelopes" + where +
        " ORDER BY observed_at,envelope_id", params
    ).fetchall()]
    decisions = [dict(row) for row in connection.execute(
        "SELECT decision_id,envelope_id,outcome,candidate_revision,observed_at,authority_effect,write_authorized "
        "FROM promotion_decisions ORDER BY observed_at,decision_id"
    ).fetchall()]
    if branch:
        allowed = {item["envelope_id"] for item in envelopes}
        decisions = [item for item in decisions if item["envelope_id"] in allowed]
    return {"envelopes": envelopes, "decisions": decisions}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("request", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("--envelope", required=True)
    verify.add_argument("verification", type=Path)
    listing = sub.add_parser("list")
    listing.add_argument("--branch")
    args = parser.parse_args()
    try:
        connection = connect_runtime(args.db.resolve())
        try:
            if args.command == "propose":
                result = persist_envelope(connection, json.loads(args.request.read_text(encoding="utf-8")))
            elif args.command == "verify":
                result = persist_decision(
                    connection, args.envelope, json.loads(args.verification.read_text(encoding="utf-8"))
                )
            else:
                result = list_promotions(connection, args.branch)
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
