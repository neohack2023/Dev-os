#!/usr/bin/env python3
"""Governed GitHub remote-authority adapter for successful MASON receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    from .db_runtime import connect_runtime
except ImportError:
    from db_runtime import connect_runtime

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = DEVOS_ROOT / "state" / "devos-knowledge.db"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_GRANT = "GITHUB_PR_MERGE"
_REMOTE_EFFECT = "GITHUB_TARGET_BRANCH_UPDATED"
_API_VERSION = "2026-03-10"
_UNSUPPORTED_RULES = {"merge_queue", "required_linear_history", "required_deployments"}


def _canon(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}:" + hashlib.sha256(_canon(payload).encode()).hexdigest()[:24]


def _required_text(mapping: dict, key: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


class GitHubClient:
    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        if not token.strip():
            raise ValueError("GitHub token is required")
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")

    def request(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.api_base + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": "DevOS-GitHub-Authority",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return {} if not raw else json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
                message = payload.get("message", raw)
            except json.JSONDecodeError:
                message = raw
            raise ValueError(f"GitHub API {method} {path} failed ({exc.code}): {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API unavailable: {exc.reason}") from exc

    def branch(self, repository: str, branch: str) -> dict:
        return self.request("GET", f"/repos/{repository}/branches/{urllib.parse.quote(branch, safe='')}")

    def rules(self, repository: str, branch: str) -> list[dict]:
        result = self.request("GET", f"/repos/{repository}/rules/branches/{urllib.parse.quote(branch, safe='')}?per_page=100")
        if not isinstance(result, list):
            raise ValueError("GitHub rules response is not a list")
        return result

    def protection(self, repository: str, branch: str) -> dict | None:
        try:
            result = self.request("GET", f"/repos/{repository}/branches/{urllib.parse.quote(branch, safe='')}/protection")
            return result if isinstance(result, dict) else None
        except ValueError as exc:
            # Active rulesets are observable with metadata-read access. Legacy branch
            # protection details can require stronger administration-read permission.
            # Treat 403/404 as unavailable supplemental policy, then let observe_policy
            # fail closed only when the active rules are also insufficient.
            if "(403)" in str(exc) or "(404)" in str(exc):
                return None
            raise

    def open_prs(self, repository: str, head: str, base: str) -> list[dict]:
        owner = repository.split("/", 1)[0]
        query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{head}", "base": base, "per_page": 100})
        result = self.request("GET", f"/repos/{repository}/pulls?{query}")
        return result if isinstance(result, list) else []

    def create_pr(self, repository: str, head: str, base: str, title: str, body: str) -> dict:
        return self.request("POST", f"/repos/{repository}/pulls", {"head": head, "base": base, "title": title, "body": body})

    def pr(self, repository: str, number: int) -> dict:
        return self.request("GET", f"/repos/{repository}/pulls/{number}")

    def reviews(self, repository: str, number: int) -> list[dict]:
        result = self.request("GET", f"/repos/{repository}/pulls/{number}/reviews?per_page=100")
        return result if isinstance(result, list) else []

    def status(self, repository: str, revision: str) -> dict:
        result = self.request("GET", f"/repos/{repository}/commits/{revision}/status")
        return result if isinstance(result, dict) else {}

    def check_runs(self, repository: str, revision: str) -> list[dict]:
        result = self.request("GET", f"/repos/{repository}/commits/{revision}/check-runs?per_page=100")
        return list(result.get("check_runs", [])) if isinstance(result, dict) else []

    def merge_pr(self, repository: str, number: int, revision: str) -> dict:
        return self.request("PUT", f"/repos/{repository}/pulls/{number}/merge", {"sha": revision, "merge_method": "merge"})

    def commit(self, repository: str, revision: str) -> dict:
        result = self.request("GET", f"/repos/{repository}/commits/{revision}")
        return result if isinstance(result, dict) else {}


def _load_mason_chain(connection: sqlite3.Connection, mason_receipt_id: str) -> tuple[dict, dict]:
    row = connection.execute(
        "SELECT plan_id,outcome,payload_json FROM mason_execution_receipts WHERE receipt_id=?", (mason_receipt_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown MASON receipt: {mason_receipt_id}")
    receipt = json.loads(row["payload_json"])
    if row["outcome"] != "APPLIED" or receipt.get("outcome") != "APPLIED":
        raise ValueError("GitHub authority requires an APPLIED MASON receipt")
    if receipt.get("remote_authority_effect") != "NONE" or receipt.get("remote_write_performed") is not False:
        raise ValueError("MASON receipt already claims remote authority/write")
    if receipt.get("post_revision") != receipt.get("candidate_revision"):
        raise ValueError("MASON receipt does not preserve exact candidate revision")
    plan_row = connection.execute(
        "SELECT payload_json FROM mason_execution_plans WHERE plan_id=?", (row["plan_id"],)
    ).fetchone()
    if plan_row is None:
        raise ValueError(f"missing MASON plan: {row['plan_id']}")
    plan = json.loads(plan_row["payload_json"])
    if plan.get("candidate_revision") != receipt.get("candidate_revision"):
        raise ValueError("MASON plan/receipt candidate mismatch")
    return receipt, plan


def _required_checks(rules: list[dict], protection: dict | None) -> list[str]:
    checks: set[str] = set()
    for rule in rules:
        if rule.get("type") == "required_status_checks":
            params = rule.get("parameters") or {}
            for item in params.get("required_status_checks", []):
                name = str(item.get("context", "")).strip()
                if name:
                    checks.add(name)
    if protection:
        status = protection.get("required_status_checks") or {}
        for name in status.get("contexts", []) or []:
            if str(name).strip():
                checks.add(str(name).strip())
        for item in status.get("checks", []) or []:
            if str(item.get("context", "")).strip():
                checks.add(str(item["context"]).strip())
    return sorted(checks)


def _required_approvals(rules: list[dict], protection: dict | None) -> int:
    count = 0
    for rule in rules:
        if rule.get("type") == "pull_request":
            params = rule.get("parameters") or {}
            count = max(count, int(params.get("required_approving_review_count", 0) or 0))
    if protection:
        reviews = protection.get("required_pull_request_reviews") or {}
        count = max(count, int(reviews.get("required_approving_review_count", 0) or 0))
    return count


def observe_policy(client, repository: str, target_branch: str) -> dict:
    branch = client.branch(repository, target_branch)
    rules = client.rules(repository, target_branch)
    protection = client.protection(repository, target_branch)
    protected = bool(branch.get("protected"))
    rule_types = sorted({str(rule.get("type", "")) for rule in rules if str(rule.get("type", ""))})
    unsupported = sorted(set(rule_types) & _UNSUPPORTED_RULES)
    requires_pr = "pull_request" in rule_types or bool((protection or {}).get("required_pull_request_reviews"))
    required_checks = _required_checks(rules, protection)
    approvals = _required_approvals(rules, protection)
    policy = {
        "target_branch": target_branch,
        "protected": protected,
        "rule_types": rule_types,
        "requires_pull_request": requires_pr,
        "required_checks": required_checks,
        "required_approvals": approvals,
        "unsupported_rules": unsupported,
        "protection_observable": protection is not None,
    }
    if not protected and not rules:
        raise ValueError("GitHub target branch has no active protection/ruleset; remote authority is not governed")
    if protected and protection is None and not rules:
        raise ValueError("GitHub protection exists but its policy cannot be inspected; refusing unverifiable authority")
    if unsupported:
        raise ValueError("unsupported GitHub authority policy: " + ", ".join(unsupported))
    if not requires_pr:
        raise ValueError("GitHub policy does not require pull-request review; refusing direct remote authority")
    if not required_checks:
        raise ValueError("GitHub policy has no required status checks; remote authority gate is incomplete")
    policy["policy_digest"] = hashlib.sha256(_canon(policy).encode()).hexdigest()
    return policy


def _authorization(request: dict, receipt: dict, plan: dict, candidate_branch: str) -> dict:
    auth = request.get("authorization")
    if not isinstance(auth, dict) or auth.get("approved") is not True:
        raise ValueError("explicit GitHub authority authorization is required")
    expected = {
        "mason_receipt_id": receipt["receipt_id"],
        "candidate_revision": receipt["candidate_revision"],
        "repository": plan["repository"],
        "target_branch": plan["target_branch"],
        "candidate_branch": candidate_branch,
    }
    if _required_text(auth, "grant") != _GRANT:
        raise ValueError(f"authorization grant must be {_GRANT}")
    for key, value in expected.items():
        if _required_text(auth, key) != value:
            raise ValueError(f"authorization {key} does not match MASON handoff")
    return {
        "authorization_id": _required_text(auth, "authorization_id"),
        "source": _required_text(auth, "source"),
        "actor": _required_text(auth, "actor"),
        "observed_at": _required_text(auth, "observed_at"),
        "grant": _GRANT,
        **expected,
        "approved": True,
    }


def prepare_remote(connection: sqlite3.Connection, mason_receipt_id: str, client, request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("GitHub authority request must be an object")
    observed_at = _required_text(request, "observed_at")
    candidate_branch = _required_text(request, "candidate_branch")
    receipt, mason_plan = _load_mason_chain(connection, mason_receipt_id)
    repository = mason_plan["repository"]
    target_branch = mason_plan["target_branch"]
    candidate_revision = receipt["candidate_revision"]
    base_revision = receipt["base_revision"]
    if not _SHA40.fullmatch(candidate_revision) or not _SHA40.fullmatch(base_revision):
        raise ValueError("MASON revisions are not canonical Git SHAs")
    target = client.branch(repository, target_branch)
    candidate = client.branch(repository, candidate_branch)
    if str(target.get("commit", {}).get("sha", "")) != base_revision:
        raise ValueError("remote target branch drifted from the MASON base revision")
    if str(candidate.get("commit", {}).get("sha", "")) != candidate_revision:
        raise ValueError("remote candidate branch does not point to the exact MASON candidate revision")
    policy = observe_policy(client, repository, target_branch)
    auth = _authorization(request, receipt, mason_plan, candidate_branch)
    payload = {
        "schema_version": 1,
        "mason_receipt_id": mason_receipt_id,
        "mason_plan_id": mason_plan["plan_id"],
        "repository": repository,
        "target_branch": target_branch,
        "candidate_branch": candidate_branch,
        "base_revision": base_revision,
        "candidate_revision": candidate_revision,
        "change_digest": receipt["change_digest"],
        "merge_method": "merge",
        "authorization": auth,
        "authorization_digest": hashlib.sha256(_canon(auth).encode()).hexdigest(),
        "policy": policy,
        "policy_digest": policy["policy_digest"],
        "prepared_at": observed_at,
        "remote_write_authorized": True,
        "authority_state": "PR_REQUIRED",
    }
    payload["plan_id"] = _stable_id("github-authority-plan", payload)
    encoded = _canon(payload)
    existing = connection.execute("SELECT payload_json FROM github_authority_plans WHERE plan_id=?", (payload["plan_id"],)).fetchone()
    if existing is not None:
        if existing["payload_json"] != encoded:
            raise ValueError(f"immutable GitHub authority plan conflict: {payload['plan_id']}")
        return {"plan": payload, "replayed": True}
    connection.execute(
        "INSERT INTO github_authority_plans(plan_id,mason_receipt_id,mason_plan_id,repository,target_branch,candidate_branch,base_revision,candidate_revision,change_digest,authorization_digest,policy_digest,payload_json,prepared_at,remote_write_authorized) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (payload["plan_id"], mason_receipt_id, mason_plan["plan_id"], repository, target_branch, candidate_branch, base_revision, candidate_revision, receipt["change_digest"], payload["authorization_digest"], payload["policy_digest"], encoded, observed_at),
    )
    connection.commit()
    return {"plan": payload, "replayed": False}


def _load_plan(connection: sqlite3.Connection, plan_id: str) -> dict:
    row = connection.execute("SELECT payload_json FROM github_authority_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown GitHub authority plan: {plan_id}")
    return json.loads(row["payload_json"])


def open_pr(connection: sqlite3.Connection, plan_id: str, client, observed_at: str) -> dict:
    plan = _load_plan(connection, plan_id)
    existing = connection.execute("SELECT payload_json FROM github_authority_prs WHERE plan_id=?", (plan_id,)).fetchone()
    if existing is not None:
        return {"pr": json.loads(existing["payload_json"]), "replayed": True}
    if client.branch(plan["repository"], plan["target_branch"])["commit"]["sha"] != plan["base_revision"]:
        raise ValueError("remote target branch drifted after GitHub authority preparation")
    if client.branch(plan["repository"], plan["candidate_branch"])["commit"]["sha"] != plan["candidate_revision"]:
        raise ValueError("remote candidate branch drifted after GitHub authority preparation")
    current_policy = observe_policy(client, plan["repository"], plan["target_branch"])
    if current_policy["policy_digest"] != plan["policy_digest"]:
        raise ValueError("GitHub authority policy changed after preparation")
    matches = client.open_prs(plan["repository"], plan["candidate_branch"], plan["target_branch"])
    if matches:
        pr = matches[0]
    else:
        pr = client.create_pr(
            plan["repository"], plan["candidate_branch"], plan["target_branch"],
            f"DevOS governed promotion {plan['candidate_revision'][:12]}",
            f"MASON receipt `{plan['mason_receipt_id']}`\n\nCandidate `{plan['candidate_revision']}`\nChange digest `{plan['change_digest']}`",
        )
    head_sha = str(pr.get("head", {}).get("sha", ""))
    if head_sha != plan["candidate_revision"]:
        raise ValueError("GitHub PR head does not equal the authorized candidate revision")
    if str(pr.get("base", {}).get("ref", "")) != plan["target_branch"]:
        raise ValueError("GitHub PR base does not equal the authorized target branch")
    number = int(pr["number"])
    binding = {
        "schema_version": 1,
        "plan_id": plan_id,
        "pr_number": number,
        "head_revision": head_sha,
        "base_branch": plan["target_branch"],
        "html_url": str(pr.get("html_url", "")),
        "observed_at": str(observed_at).strip(),
    }
    binding["pr_binding_id"] = _stable_id("github-pr-binding", binding)
    connection.execute(
        "INSERT INTO github_authority_prs(pr_binding_id,plan_id,pr_number,head_revision,base_branch,html_url,payload_json,observed_at) VALUES (?,?,?,?,?,?,?,?)",
        (binding["pr_binding_id"], plan_id, number, head_sha, plan["target_branch"], binding["html_url"], _canon(binding), binding["observed_at"]),
    )
    connection.commit()
    return {"pr": binding, "replayed": False}


def _check_states(client, repository: str, revision: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for item in client.status(repository, revision).get("statuses", []) or []:
        states[str(item.get("context", ""))] = str(item.get("state", "")).lower()
    for item in client.check_runs(repository, revision):
        name = str(item.get("name", ""))
        conclusion = str(item.get("conclusion", "")).lower()
        if name:
            states[name] = conclusion
    return states


def verify_ready(connection: sqlite3.Connection, plan_id: str, client) -> dict:
    plan = _load_plan(connection, plan_id)
    row = connection.execute("SELECT pr_number FROM github_authority_prs WHERE plan_id=?", (plan_id,)).fetchone()
    if row is None:
        raise ValueError("GitHub authority plan has no bound pull request")
    pr = client.pr(plan["repository"], int(row["pr_number"]))
    reasons: list[str] = []
    if str(pr.get("state")) != "open": reasons.append("pull request is not open")
    if str(pr.get("head", {}).get("sha", "")) != plan["candidate_revision"]: reasons.append("pull request head drifted")
    if str(pr.get("base", {}).get("ref", "")) != plan["target_branch"]: reasons.append("pull request base drifted")
    target_sha = str(client.branch(plan["repository"], plan["target_branch"]).get("commit", {}).get("sha", ""))
    if target_sha != plan["base_revision"]: reasons.append("target branch is no longer at authorized base revision")
    policy = observe_policy(client, plan["repository"], plan["target_branch"])
    if policy["policy_digest"] != plan["policy_digest"]: reasons.append("GitHub policy changed after preparation")
    states = _check_states(client, plan["repository"], plan["candidate_revision"])
    for name in plan["policy"]["required_checks"]:
        if states.get(name) not in {"success", "neutral", "skipped"}:
            reasons.append(f"required check not successful on latest candidate SHA: {name}")
    approvals = set()
    for review in client.reviews(plan["repository"], int(row["pr_number"])):
        if str(review.get("state", "")).upper() == "APPROVED":
            login = str(review.get("user", {}).get("login", "")).strip()
            if login: approvals.add(login)
    if len(approvals) < int(plan["policy"]["required_approvals"]):
        reasons.append("required approving review count not satisfied")
    if pr.get("mergeable") is not True:
        reasons.append("GitHub does not currently report the pull request mergeable")
    return {
        "ready": not reasons,
        "reasons": sorted(set(reasons)),
        "pr_number": int(row["pr_number"]),
        "candidate_revision": plan["candidate_revision"],
        "target_revision": target_sha,
        "check_states": states,
        "approval_count": len(approvals),
        "policy_digest": policy["policy_digest"],
    }


def merge_remote(connection: sqlite3.Connection, plan_id: str, client, observed_at: str) -> dict:
    prior = connection.execute("SELECT payload_json FROM github_authority_receipts WHERE plan_id=?", (plan_id,)).fetchone()
    if prior is not None:
        return {"receipt": json.loads(prior["payload_json"]), "replayed": True}
    plan = _load_plan(connection, plan_id)
    readiness = verify_ready(connection, plan_id, client)
    if not readiness["ready"]:
        raise ValueError("GitHub authority is not ready: " + "; ".join(readiness["reasons"]))
    number = readiness["pr_number"]
    response = client.merge_pr(plan["repository"], number, plan["candidate_revision"])
    if not bool(response.get("merged")):
        raise ValueError("GitHub did not merge the authorized pull request: " + str(response.get("message", "unknown reason")))
    authoritative_revision = str(response.get("sha", ""))
    if not _SHA40.fullmatch(authoritative_revision):
        raise ValueError("GitHub merge response did not provide an authoritative commit SHA")
    target = client.branch(plan["repository"], plan["target_branch"])
    if str(target.get("commit", {}).get("sha", "")) != authoritative_revision:
        raise RuntimeError("remote target branch does not match GitHub merge result")
    commit = client.commit(plan["repository"], authoritative_revision)
    parents = [str(item.get("sha", "")) for item in commit.get("parents", [])]
    if plan["candidate_revision"] not in parents:
        raise RuntimeError("authoritative merge commit does not preserve the exact candidate as a parent")
    receipt = {
        "schema_version": 1,
        "plan_id": plan_id,
        "mason_receipt_id": plan["mason_receipt_id"],
        "pr_number": number,
        "repository": plan["repository"],
        "target_branch": plan["target_branch"],
        "base_revision": plan["base_revision"],
        "candidate_revision": plan["candidate_revision"],
        "authoritative_revision": authoritative_revision,
        "candidate_is_authoritative_parent": True,
        "change_digest": plan["change_digest"],
        "policy_digest": plan["policy_digest"],
        "observed_at": str(observed_at).strip(),
        "outcome": "MERGED",
        "remote_authority_effect": _REMOTE_EFFECT,
        "remote_write_performed": True,
    }
    receipt["receipt_id"] = _stable_id("github-authority-receipt", receipt)
    connection.execute(
        "INSERT INTO github_authority_receipts(receipt_id,plan_id,pr_number,outcome,candidate_revision,authoritative_revision,policy_digest,payload_json,observed_at,remote_authority_effect,remote_write_performed) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
        (receipt["receipt_id"], plan_id, number, "MERGED", plan["candidate_revision"], authoritative_revision, plan["policy_digest"], _canon(receipt), receipt["observed_at"], _REMOTE_EFFECT),
    )
    connection.commit()
    return {"receipt": receipt, "replayed": False}


def list_authority(connection: sqlite3.Connection) -> dict:
    return {
        "plans": [dict(r) for r in connection.execute("SELECT plan_id,mason_receipt_id,repository,target_branch,candidate_branch,candidate_revision,policy_digest,prepared_at,remote_write_authorized FROM github_authority_plans ORDER BY prepared_at,plan_id")],
        "prs": [dict(r) for r in connection.execute("SELECT plan_id,pr_number,head_revision,base_branch,html_url,observed_at FROM github_authority_prs ORDER BY observed_at,pr_number")],
        "receipts": [dict(r) for r in connection.execute("SELECT receipt_id,plan_id,pr_number,outcome,candidate_revision,authoritative_revision,policy_digest,observed_at,remote_authority_effect,remote_write_performed FROM github_authority_receipts ORDER BY observed_at,receipt_id")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--mason-receipt", required=True)
    prepare.add_argument("request", type=Path)
    opening = sub.add_parser("open-pr")
    opening.add_argument("--plan", required=True)
    opening.add_argument("--observed-at", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--plan", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--plan", required=True)
    merge.add_argument("--observed-at", required=True)
    sub.add_parser("list")
    args = parser.parse_args()
    try:
        connection = connect_runtime(args.db.resolve())
        try:
            if args.command == "list":
                result = list_authority(connection)
            else:
                token = os.environ.get(args.token_env, "")
                client = GitHubClient(token)
                if args.command == "prepare":
                    result = prepare_remote(connection, args.mason_receipt, client, json.loads(args.request.read_text(encoding="utf-8")))
                elif args.command == "open-pr":
                    result = open_pr(connection, args.plan, client, args.observed_at)
                elif args.command == "verify":
                    result = {"verification": verify_ready(connection, args.plan, client)}
                else:
                    result = merge_remote(connection, args.plan, client, args.observed_at)
        finally:
            connection.close()
        print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
