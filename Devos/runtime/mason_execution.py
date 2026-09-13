#!/usr/bin/env python3
"""Portable MASON local Git executor for verified DevOS promotion handoffs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

try:
    from .db_runtime import connect_runtime
except ImportError:
    from db_runtime import connect_runtime

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = DEVOS_ROOT / "state" / "devos-knowledge.db"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_GRANT = "MASON_FAST_FORWARD"
_LOCAL_EFFECT = "LOCAL_GIT_REF_UPDATED"
_REMOTE_EFFECT = "NONE"
_DIGEST_ALGORITHM = "sha256-git-diff-v1"


def _canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}:" + hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()[:24]


def _required_text(mapping: dict, key: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _git(repo_root: Path, *args: str, check: bool = True, text: bool = True):
    env = os.environ.copy()
    env.update({
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    })
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=text,
        env=env,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {stderr}")
    return result


def _git_text(repo_root: Path, *args: str) -> str:
    return _git(repo_root, *args).stdout.strip()


def _repo_root(path: Path) -> Path:
    requested = Path(path).resolve()
    actual = Path(_git_text(requested, "rev-parse", "--show-toplevel")).resolve()
    if actual != requested:
        raise ValueError(f"repo_root must be the Git top-level: {actual}")
    return actual


def _head(repo_root: Path) -> str:
    value = _git_text(repo_root, "rev-parse", "HEAD")
    if not _SHA40.fullmatch(value):
        raise ValueError("unable to resolve current Git HEAD")
    return value


def _branch(repo_root: Path) -> str:
    value = _git_text(repo_root, "branch", "--show-current")
    if not value:
        raise ValueError("MASON refuses detached HEAD execution")
    return value


def _clean(repo_root: Path) -> bool:
    return _git_text(repo_root, "status", "--porcelain=v1", "--untracked-files=all") == ""


def _reject_active_filters(repo_root: Path) -> None:
    result = _git(
        repo_root,
        "config",
        "--local",
        "--get-regexp",
        r"^filter\..*\.(smudge|process)$",
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        raise ValueError("MASON refuses repositories with active local smudge/process filter commands")
    if result.returncode not in (0, 1):
        raise ValueError("unable to inspect local Git filter configuration")


def _assert_commit(repo_root: Path, revision: str) -> None:
    if not _SHA40.fullmatch(revision):
        raise ValueError("candidate revision must be a 40-character lowercase Git SHA")
    result = _git(repo_root, "cat-file", "-e", f"{revision}^{{commit}}", check=False)
    if result.returncode != 0:
        raise ValueError(f"candidate revision is not a local Git commit: {revision}")


def _is_ancestor(repo_root: Path, base_revision: str, candidate_revision: str) -> bool:
    result = _git(repo_root, "merge-base", "--is-ancestor", base_revision, candidate_revision, check=False)
    if result.returncode not in (0, 1):
        raise ValueError("unable to verify candidate ancestry")
    return result.returncode == 0


def _changed_paths(repo_root: Path, base_revision: str, candidate_revision: str) -> list[str]:
    output = _git_text(
        repo_root, "diff", "--name-only", "--no-renames", base_revision, candidate_revision, "--"
    )
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def compute_change_digest(repo_root: Path, base_revision: str, candidate_revision: str) -> str:
    result = _git(
        repo_root,
        "diff",
        "--binary",
        "--full-index",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        base_revision,
        candidate_revision,
        "--",
        text=False,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def _load_handoff(connection: sqlite3.Connection, decision_id: str) -> tuple[dict, dict]:
    row = connection.execute(
        "SELECT envelope_id,outcome,payload_json FROM promotion_decisions WHERE decision_id=?",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown promotion decision: {decision_id}")
    decision = json.loads(row["payload_json"])
    if str(row["outcome"]) != "PROMOTE" or decision.get("outcome") != "PROMOTE":
        raise ValueError("MASON execution requires a PROMOTE decision")
    if decision.get("next_action") != "MASON_REVIEW_PROMOTION":
        raise ValueError("promotion decision is not a MASON promotion handoff")
    if bool(decision.get("write_authorized", True)):
        raise ValueError("promotion gate must not pre-authorize repository writes")
    envelope_row = connection.execute(
        "SELECT payload_json FROM promotion_envelopes WHERE envelope_id=?", (row["envelope_id"],)
    ).fetchone()
    if envelope_row is None:
        raise ValueError(f"missing promotion envelope: {row['envelope_id']}")
    envelope = json.loads(envelope_row["payload_json"])
    if envelope.get("stone_state") != "LOCKED":
        raise ValueError("MASON requires a locked STONE envelope")
    if envelope.get("mason_state") != "HANDOFF_REQUIRED":
        raise ValueError("promotion envelope is not awaiting MASON handoff")
    if decision.get("candidate_revision") != envelope.get("candidate_revision"):
        raise ValueError("promotion decision/envelope candidate revision mismatch")
    return decision, envelope


def _normalize_authorization(
    request: dict, decision: dict, envelope: dict, target_branch: str
) -> dict:
    authorization = request.get("authorization")
    if not isinstance(authorization, dict):
        raise ValueError("authorization must be an object")
    if authorization.get("approved") is not True:
        raise ValueError("explicit MASON authorization is required")
    if _required_text(authorization, "grant") != _GRANT:
        raise ValueError(f"authorization grant must be {_GRANT}")
    expected = {
        "decision_id": decision["decision_id"],
        "envelope_id": envelope["envelope_id"],
        "candidate_revision": envelope["candidate_revision"],
        "target_branch": target_branch,
        "scope": envelope["required_authorization"],
    }
    for key, value in expected.items():
        if _required_text(authorization, key) != value:
            raise ValueError(f"authorization {key} does not match locked promotion handoff")
    payload = {
        "authorization_id": _required_text(authorization, "authorization_id"),
        "source": _required_text(authorization, "source"),
        "actor": _required_text(authorization, "actor"),
        "observed_at": _required_text(authorization, "observed_at"),
        "grant": _GRANT,
        **expected,
        "approved": True,
    }
    return payload


def preflight(
    repo_root: Path, envelope: dict, base_revision: str, *, require_head_at_base: bool = True
) -> dict:
    repo_root = _repo_root(repo_root)
    candidate_revision = str(envelope["candidate_revision"])
    _assert_commit(repo_root, base_revision)
    _assert_commit(repo_root, candidate_revision)
    target_branch = str(envelope["target"]["branch"])
    current_branch = _branch(repo_root)
    if current_branch != target_branch:
        raise ValueError(f"target branch mismatch: {current_branch} != {target_branch}")
    current_head = _head(repo_root)
    if require_head_at_base and current_head != base_revision:
        raise ValueError(f"base revision mismatch: HEAD {current_head} != {base_revision}")
    if not _clean(repo_root):
        raise ValueError("MASON refuses execution with a dirty Git worktree")
    _reject_active_filters(repo_root)
    if base_revision == candidate_revision:
        raise ValueError("candidate revision is already the base revision")
    if not _is_ancestor(repo_root, base_revision, candidate_revision):
        raise ValueError("candidate revision is not a fast-forward descendant of base revision")
    changed_paths = _changed_paths(repo_root, base_revision, candidate_revision)
    expected_paths = sorted(str(path) for path in envelope["target"]["paths"])
    if changed_paths != expected_paths:
        raise ValueError(
            f"candidate changed-path set differs from locked STONE target: {changed_paths} != {expected_paths}"
        )
    digest = compute_change_digest(repo_root, base_revision, candidate_revision)
    if digest != envelope["change_digest"]:
        raise ValueError("candidate Git diff digest does not match locked STONE change_digest")
    return {
        "base_revision": base_revision,
        "candidate_revision": candidate_revision,
        "target_branch": target_branch,
        "pre_head": current_head,
        "changed_paths": changed_paths,
        "change_digest": digest,
        "change_digest_algorithm": _DIGEST_ALGORITHM,
    }


def prepare_execution(
    connection: sqlite3.Connection, decision_id: str, repo_root: Path, request: dict
) -> dict:
    if not isinstance(request, dict):
        raise ValueError("execution request must be a JSON object")
    observed_at = _required_text(request, "observed_at")
    base_revision = _required_text(request, "base_revision")
    if not _SHA40.fullmatch(base_revision):
        raise ValueError("base_revision must be a 40-character lowercase Git SHA")
    decision, envelope = _load_handoff(connection, decision_id)
    target_branch = str(envelope["target"]["branch"])
    authorization = _normalize_authorization(request, decision, envelope, target_branch)
    state = preflight(Path(repo_root), envelope, base_revision)
    payload = {
        "schema_version": 1,
        "decision_id": decision_id,
        "envelope_id": envelope["envelope_id"],
        "repository": envelope["target"]["repository"],
        "target_branch": target_branch,
        "base_revision": base_revision,
        "candidate_revision": envelope["candidate_revision"],
        "change_digest": envelope["change_digest"],
        "change_digest_algorithm": _DIGEST_ALGORITHM,
        "changed_paths": state["changed_paths"],
        "authorization": authorization,
        "authorization_digest": hashlib.sha256(_canon(authorization).encode("utf-8")).hexdigest(),
        "prepared_at": observed_at,
        "execution_mode": "LOCAL_GIT_FAST_FORWARD",
        "local_execution_authorized": True,
        "remote_write_authorized": False,
        "remote_write_performed": False,
    }
    payload["plan_id"] = _stable_id("mason-plan", payload)
    encoded = _canon(payload)
    existing = connection.execute(
        "SELECT payload_json FROM mason_execution_plans WHERE plan_id=?", (payload["plan_id"],)
    ).fetchone()
    if existing is not None:
        if existing["payload_json"] != encoded:
            raise ValueError(f"immutable MASON plan conflict: {payload['plan_id']}")
        return {"plan": payload, "replayed": True}
    connection.execute(
        "INSERT INTO mason_execution_plans("
        "plan_id,decision_id,envelope_id,target_branch,base_revision,candidate_revision,change_digest,"
        "authorization_digest,payload_json,prepared_at,local_execution_authorized,remote_write_authorized"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,1,0)",
        (
            payload["plan_id"],
            decision_id,
            envelope["envelope_id"],
            target_branch,
            base_revision,
            envelope["candidate_revision"],
            envelope["change_digest"],
            payload["authorization_digest"],
            encoded,
            observed_at,
        ),
    )
    connection.commit()
    return {"plan": payload, "replayed": False}


def _failure_receipt(
    plan: dict, observed_at: str, repo_root: Path, error: str
) -> dict:
    try:
        post_head = _head(repo_root)
        current_branch = _branch(repo_root)
        clean = _clean(repo_root)
        tree_sha = _git_text(repo_root, "rev-parse", "HEAD^{tree}")
    except Exception:
        post_head = ""
        current_branch = ""
        clean = False
        tree_sha = ""
    return {
        "schema_version": 1,
        "plan_id": plan["plan_id"],
        "decision_id": plan["decision_id"],
        "envelope_id": plan["envelope_id"],
        "observed_at": observed_at,
        "outcome": "FAILED",
        "base_revision": plan["base_revision"],
        "candidate_revision": plan["candidate_revision"],
        "post_revision": post_head,
        "target_branch": plan["target_branch"],
        "post_branch": current_branch,
        "post_tree_sha": tree_sha,
        "changed_paths": plan["changed_paths"],
        "change_digest": plan["change_digest"],
        "change_digest_algorithm": _DIGEST_ALGORITHM,
        "working_tree_clean": clean,
        "error": error,
        "local_authority_effect": "NONE",
        "remote_authority_effect": _REMOTE_EFFECT,
        "remote_write_performed": False,
        "rollback_revision": plan["base_revision"],
    }


def _persist_receipt(connection: sqlite3.Connection, receipt: dict) -> dict:
    receipt["receipt_id"] = _stable_id("mason-receipt", receipt)
    encoded = _canon(receipt)
    existing = connection.execute(
        "SELECT receipt_id,payload_json FROM mason_execution_receipts WHERE plan_id=?",
        (receipt["plan_id"],),
    ).fetchone()
    if existing is not None:
        stored = json.loads(existing["payload_json"])
        return {"receipt": stored, "replayed": True}
    connection.execute(
        "INSERT INTO mason_execution_receipts("
        "receipt_id,plan_id,outcome,base_revision,post_revision,change_digest,payload_json,observed_at,"
        "local_authority_effect,remote_authority_effect,remote_write_performed"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,0)",
        (
            receipt["receipt_id"],
            receipt["plan_id"],
            receipt["outcome"],
            receipt["base_revision"],
            receipt["post_revision"],
            receipt["change_digest"],
            encoded,
            receipt["observed_at"],
            receipt["local_authority_effect"],
            receipt["remote_authority_effect"],
        ),
    )
    connection.commit()
    return {"receipt": receipt, "replayed": False}


def apply_execution(
    connection: sqlite3.Connection, plan_id: str, repo_root: Path, observed_at: str
) -> dict:
    observed_at = str(observed_at).strip()
    if not observed_at:
        raise ValueError("observed_at is required")
    existing = connection.execute(
        "SELECT payload_json FROM mason_execution_receipts WHERE plan_id=?", (plan_id,)
    ).fetchone()
    if existing is not None:
        stored = json.loads(existing["payload_json"])
        if stored.get("outcome") != "APPLIED":
            raise RuntimeError(
                f"MASON execution previously failed; immutable receipt {stored.get('receipt_id','')}: "
                f"{stored.get('error','')}"
            )
        return {"receipt": stored, "replayed": True}
    row = connection.execute(
        "SELECT payload_json FROM mason_execution_plans WHERE plan_id=?", (plan_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown MASON plan: {plan_id}")
    plan = json.loads(row["payload_json"])
    decision, envelope = _load_handoff(connection, plan["decision_id"])
    if envelope["envelope_id"] != plan["envelope_id"]:
        raise ValueError("MASON plan/envelope identity mismatch")
    if envelope["candidate_revision"] != plan["candidate_revision"]:
        raise ValueError("MASON plan candidate drift")
    if envelope["change_digest"] != plan["change_digest"]:
        raise ValueError("MASON plan change digest drift")
    repo_root = _repo_root(Path(repo_root))
    try:
        preflight(repo_root, envelope, plan["base_revision"])
        _git(repo_root, "merge", "--ff-only", "--no-edit", plan["candidate_revision"])
        post_head = _head(repo_root)
        post_branch = _branch(repo_root)
        clean = _clean(repo_root)
        if post_head != plan["candidate_revision"]:
            raise ValueError("post-execution HEAD does not equal candidate revision")
        if post_branch != plan["target_branch"]:
            raise ValueError("post-execution branch drift")
        if not clean:
            raise ValueError("post-execution worktree is not clean")
        changed_paths = _changed_paths(repo_root, plan["base_revision"], post_head)
        if changed_paths != plan["changed_paths"]:
            raise ValueError("post-execution changed-path verification failed")
        digest = compute_change_digest(repo_root, plan["base_revision"], post_head)
        if digest != plan["change_digest"]:
            raise ValueError("post-execution change digest verification failed")
        tree_sha = _git_text(repo_root, "rev-parse", "HEAD^{tree}")
        receipt = {
            "schema_version": 1,
            "plan_id": plan_id,
            "decision_id": plan["decision_id"],
            "envelope_id": plan["envelope_id"],
            "observed_at": observed_at,
            "outcome": "APPLIED",
            "base_revision": plan["base_revision"],
            "candidate_revision": plan["candidate_revision"],
            "post_revision": post_head,
            "target_branch": plan["target_branch"],
            "post_branch": post_branch,
            "post_tree_sha": tree_sha,
            "changed_paths": changed_paths,
            "change_digest": digest,
            "change_digest_algorithm": _DIGEST_ALGORITHM,
            "working_tree_clean": True,
            "error": "",
            "local_authority_effect": _LOCAL_EFFECT,
            "remote_authority_effect": _REMOTE_EFFECT,
            "remote_write_performed": False,
            "rollback_revision": plan["base_revision"],
        }
    except Exception as exc:
        receipt = _failure_receipt(plan, observed_at, repo_root, str(exc))
    result = _persist_receipt(connection, receipt)
    if result["receipt"]["outcome"] != "APPLIED":
        raise RuntimeError(
            f"MASON execution failed; immutable receipt {result['receipt']['receipt_id']}: "
            f"{result['receipt']['error']}"
        )
    return result


def list_executions(connection: sqlite3.Connection) -> dict:
    plans = [
        dict(row)
        for row in connection.execute(
            "SELECT plan_id,decision_id,envelope_id,target_branch,base_revision,candidate_revision,"
            "change_digest,prepared_at,local_execution_authorized,remote_write_authorized "
            "FROM mason_execution_plans ORDER BY prepared_at,plan_id"
        ).fetchall()
    ]
    receipts = [
        dict(row)
        for row in connection.execute(
            "SELECT receipt_id,plan_id,outcome,base_revision,post_revision,change_digest,observed_at,"
            "local_authority_effect,remote_authority_effect,remote_write_performed "
            "FROM mason_execution_receipts ORDER BY observed_at,receipt_id"
        ).fetchall()
    ]
    return {"plans": plans, "receipts": receipts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--decision", required=True)
    prepare.add_argument("--repo-root", type=Path, required=True)
    prepare.add_argument("request", type=Path)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--repo-root", type=Path, required=True)
    apply.add_argument("--observed-at", required=True)
    sub.add_parser("list")
    args = parser.parse_args()
    try:
        connection = connect_runtime(args.db.resolve())
        try:
            if args.command == "prepare":
                result = prepare_execution(
                    connection,
                    args.decision,
                    args.repo_root,
                    json.loads(args.request.read_text(encoding="utf-8")),
                )
            elif args.command == "apply":
                result = apply_execution(connection, args.plan, args.repo_root, args.observed_at)
            else:
                result = list_executions(connection)
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
