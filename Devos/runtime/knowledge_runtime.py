#!/usr/bin/env python3
"""Portable branch-aware context packet runtime for DevOS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

try:
    from .build_knowledge_db import DEFAULT_DB_NAME, build
    from .db_runtime import connect_runtime, runtime_health
    from .knowledge_lineage import current_state
    from .knowledge_trajectory import compact_trajectory, expand_trajectory
except ImportError:
    from build_knowledge_db import DEFAULT_DB_NAME, build
    from db_runtime import connect_runtime, runtime_health
    from knowledge_lineage import current_state
    from knowledge_trajectory import compact_trajectory, expand_trajectory

DEVOS_ROOT = Path(__file__).resolve().parents[1]
PACKET_SCHEMA_VERSION = 1
MAX_DOCUMENTS = 20
MAX_TASKS = 20
MAX_TOOLS = 10
MAX_KNOWLEDGE_SUBJECTS = 20
MAX_DOCUMENT_CHARS = 20000


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _tokens(query: str) -> list[str]:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9_-]+", query)]
    if not tokens:
        raise ValueError("query must contain at least one searchable token")
    return list(dict.fromkeys(tokens))


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    value = json.loads(raw)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _project_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key,value FROM project_meta ORDER BY key").fetchall()
    }


def _projection_digest(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT value FROM projection_meta WHERE key='projection_digest'"
    ).fetchone()
    return row[0] if row else None


def _branch_rows(connection: sqlite3.Connection) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT branch_key,scope_key,title,status,dependencies_json,surfaces_json "
        "FROM branch_state ORDER BY branch_key"
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        result[row["branch_key"]] = {
            "branch_key": row["branch_key"],
            "scope_key": row["scope_key"],
            "title": row["title"],
            "status": row["status"],
            "dependencies": _json_list(row["dependencies_json"]),
            "surfaces": _json_list(row["surfaces_json"]),
        }
    return result


def resolve_branches(connection: sqlite3.Connection, requested: Iterable[str]) -> tuple[list[str], dict[str, dict]]:
    index = _branch_rows(connection)
    requested_keys = list(dict.fromkeys(str(key) for key in requested if str(key).strip()))
    if not requested_keys:
        raise ValueError("at least one branch is required")
    for key in requested_keys:
        if key not in index:
            raise ValueError(f"unknown branch_key: {key}")

    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            raise ValueError(f"branch dependency cycle at {key}")
        visiting.add(key)
        for dep in index[key]["dependencies"]:
            if dep not in index:
                raise ValueError(f"{key}: unknown branch dependency {dep}")
            visit(dep)
        visiting.remove(key)
        visited.add(key)
        ordered.append(key)

    for key in requested_keys:
        visit(key)
    return ordered, index


def _surface_match(path: str, surface: str) -> bool:
    path = path.strip("/")
    surface = surface.strip().replace("\\", "/").strip("/")
    if surface in {"", "."}:
        return True
    return path == surface or path.startswith(surface + "/")


def _branch_tier(path: str, requested: list[str], resolved: list[str], index: dict[str, dict]) -> tuple[int, list[str]]:
    matched = [
        key
        for key in resolved
        if any(_surface_match(path, surface) for surface in index[key]["surfaces"])
    ]
    if not matched:
        return 99, []
    requested_set = set(requested)
    return (0 if any(key in requested_set for key in matched) else 1), matched


def _score(query: str, tokens: list[str], weighted_texts: Iterable[tuple[str, int]]) -> int:
    phrase = query.strip().lower()
    score = 0
    for text, weight in weighted_texts:
        value = (text or "").lower()
        if phrase and phrase in value:
            score += weight * 4
        for token in tokens:
            score += min(value.count(token), 3) * weight
    return score


def _excerpt(content: str, tokens: list[str], limit: int) -> str:
    if limit <= 0:
        return ""
    collapsed = re.sub(r"\s+", " ", content).strip()
    if len(collapsed) <= limit:
        return collapsed
    lower = collapsed.lower()
    positions = [lower.find(token) for token in tokens]
    positions = [pos for pos in positions if pos >= 0]
    anchor = min(positions) if positions else 0
    start = max(0, anchor - min(120, limit // 4))
    end = min(len(collapsed), start + limit)
    if end - start < limit:
        start = max(0, end - limit)
    snippet = collapsed[start:end].strip()
    if start > 0 and snippet:
        snippet = "…" + snippet[1:]
    if end < len(collapsed) and snippet:
        snippet = snippet[:-1] + "…"
    return snippet


def projection_freshness(connection: sqlite3.Connection, host_root: Path) -> dict[str, object]:
    changed: list[str] = []
    rows = connection.execute(
        "SELECT source_path,source_hash FROM build_manifest ORDER BY source_path"
    ).fetchall()
    for row in rows:
        path = host_root / row["source_path"]
        if not path.is_file():
            changed.append(row["source_path"])
            continue
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current != row["source_hash"]:
            changed.append(row["source_path"])
    return {
        "fresh": not changed,
        "checked_sources": len(rows),
        "changed_sources": changed,
    }


def _source_manifest(connection: sqlite3.Connection, paths: set[str]) -> list[dict]:
    if not paths:
        return []
    rows = connection.execute(
        "SELECT source_path,source_kind,source_hash FROM build_manifest ORDER BY source_path"
    ).fetchall()
    return [
        {"path": row["source_path"], "kind": row["source_kind"], "sha256": row["source_hash"]}
        for row in rows
        if row["source_path"] in paths
    ]


def _knowledge_states(
    connection: sqlite3.Connection,
    query: str,
    tokens: list[str],
    *,
    limit: int,
) -> list[dict[str, object]]:
    if limit == 0:
        return []
    candidates: list[dict[str, object]] = []
    rows = connection.execute(
        "SELECT subject_id,scope_key,knowledge_key,knowledge_kind FROM knowledge_subjects ORDER BY scope_key,knowledge_key"
    ).fetchall()
    for row in rows:
        assertion_rows = connection.execute(
            "SELECT payload_json FROM knowledge_assertions WHERE subject_id=? ORDER BY recorded_at,assertion_id",
            (row["subject_id"],),
        ).fetchall()
        assertion_text = " ".join(item["payload_json"] for item in assertion_rows)
        score = _score(
            query,
            tokens,
            (
                (row["knowledge_key"], 8),
                (row["scope_key"], 3),
                (row["knowledge_kind"], 2),
                (assertion_text, 1),
            ),
        )
        if score <= 0:
            continue
        candidates.append(
            {
                "subject_id": row["subject_id"],
                "scope_key": row["scope_key"],
                "knowledge_key": row["knowledge_key"],
                "knowledge_kind": row["knowledge_kind"],
                "score": score,
                "state": current_state(connection, subject_id=row["subject_id"]),
                "trajectory": compact_trajectory(connection, subject_id=row["subject_id"]),
            }
        )
    candidates.sort(key=lambda row: (-int(row["score"]), str(row["scope_key"]), str(row["knowledge_key"])))
    return candidates[:limit]


def expand_knowledge_state(connection: sqlite3.Connection, *, subject_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT subject_id,scope_key,knowledge_key,knowledge_kind FROM knowledge_subjects WHERE subject_id=?",
        (subject_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown subject_id: {subject_id}")
    return {
        "subject_id": row["subject_id"],
        "scope_key": row["scope_key"],
        "knowledge_key": row["knowledge_key"],
        "knowledge_kind": row["knowledge_kind"],
        "state": current_state(connection, subject_id=subject_id),
        "trajectory": expand_trajectory(connection, subject_id=subject_id),
    }


def build_packet(
    connection: sqlite3.Connection,
    host_root: Path,
    query: str,
    branches: list[str],
    *,
    limit_documents: int = 6,
    limit_tasks: int = 6,
    limit_tools: int = 4,
    limit_knowledge: int = 6,
    max_document_chars: int = 6000,
) -> dict[str, object]:
    if not 1 <= limit_documents <= MAX_DOCUMENTS:
        raise ValueError(f"limit_documents must be 1..{MAX_DOCUMENTS}")
    if not 0 <= limit_tasks <= MAX_TASKS:
        raise ValueError(f"limit_tasks must be 0..{MAX_TASKS}")
    if not 0 <= limit_tools <= MAX_TOOLS:
        raise ValueError(f"limit_tools must be 0..{MAX_TOOLS}")
    if not 0 <= limit_knowledge <= MAX_KNOWLEDGE_SUBJECTS:
        raise ValueError(f"limit_knowledge must be 0..{MAX_KNOWLEDGE_SUBJECTS}")
    if not 0 <= max_document_chars <= MAX_DOCUMENT_CHARS:
        raise ValueError(f"max_document_chars must be 0..{MAX_DOCUMENT_CHARS}")

    tokens = _tokens(query)
    requested = list(dict.fromkeys(branches))
    resolved, branch_index = resolve_branches(connection, requested)
    requested_set = set(requested)

    doc_candidates: list[dict] = []
    for row in connection.execute(
        "SELECT path,title,section,kind,content,content_hash FROM documents ORDER BY path,section"
    ).fetchall():
        tier, matched = _branch_tier(row["path"], requested, resolved, branch_index)
        if tier == 99:
            continue
        score = _score(
            query,
            tokens,
            (
                (row["title"], 6),
                (row["section"], 4),
                (row["path"], 3),
                (row["content"], 1),
            ),
        )
        if score <= 0:
            continue
        doc_candidates.append(
            {
                "path": row["path"],
                "title": row["title"],
                "section": row["section"],
                "kind": row["kind"],
                "content_hash": row["content_hash"],
                "branch_keys": matched,
                "branch_tier": tier,
                "score": score,
                "_content": row["content"],
            }
        )
    doc_candidates.sort(
        key=lambda row: (row["branch_tier"], -row["score"], row["path"], row["section"])
    )

    documents: list[dict] = []
    chars_left = max_document_chars
    selected_paths: set[str] = set()
    for row in doc_candidates[:limit_documents]:
        per_item = min(900, chars_left)
        if per_item <= 0:
            break
        excerpt = _excerpt(row.pop("_content"), tokens, per_item)
        chars_left -= len(excerpt)
        row["excerpt"] = excerpt
        documents.append(row)
        selected_paths.add(row["path"])

    task_rows = connection.execute(
        "SELECT * FROM devos_tasks ORDER BY priority,task_id"
    ).fetchall()
    tasks: list[dict] = []
    for row in task_rows:
        branch_keys = [
            edge["branch_key"]
            for edge in connection.execute(
                "SELECT branch_key FROM task_branches WHERE task_id=? ORDER BY ordinal,branch_key",
                (row["task_id"],),
            ).fetchall()
        ]
        matched = [key for key in branch_keys if key in resolved]
        if not matched:
            continue
        deps = [
            edge["depends_on_task_id"]
            for edge in connection.execute(
                "SELECT depends_on_task_id FROM task_dependencies WHERE task_id=? ORDER BY ordinal,depends_on_task_id",
                (row["task_id"],),
            ).fetchall()
        ]
        acceptance = _json_list(row["acceptance_json"])[:6]
        tracking = _json_list(row["tracking_json"])[:6]
        evidence = _json_list(row["evidence_refs_json"])[:6]
        score = _score(
            query,
            tokens,
            (
                (row["title"], 6),
                (row["objective"], 5),
                (" ".join(acceptance), 3),
                (" ".join(tracking), 2),
                (" ".join(evidence), 1),
            ),
        )
        tier = 0 if any(key in requested_set for key in matched) else 1
        tasks.append(
            {
                "task_id": row["task_id"],
                "title": row["title"],
                "priority": row["priority"],
                "status": row["status"],
                "task_type": row["task_type"],
                "owner_role": row["owner_role"],
                "assigned_agent": row["assigned_agent"],
                "objective": row["objective"],
                "transfer_canary": bool(row["transfer_canary"]),
                "branch_keys": branch_keys,
                "dependencies": deps,
                "tracking": tracking,
                "acceptance_criteria": acceptance,
                "evidence_refs": evidence,
                "branch_tier": tier,
                "score": score,
            }
        )
    tasks.sort(key=lambda row: (row["branch_tier"], -row["score"], row["priority"], row["task_id"]))
    tasks = tasks[:limit_tasks]

    tools: list[dict] = []
    if limit_tools:
        for row in connection.execute(
            "SELECT tool_key,repository,verified_revision,maturity,payload_json FROM tool_registry ORDER BY tool_key"
        ).fetchall():
            score = _score(
                query,
                tokens,
                (
                    (row["tool_key"], 6),
                    (row["repository"], 4),
                    (row["verified_revision"], 1),
                    (row["maturity"], 2),
                    (row["payload_json"], 1),
                ),
            )
            if score <= 0:
                continue
            tools.append(
                {
                    "tool_key": row["tool_key"],
                    "repository": row["repository"],
                    "verified_revision": row["verified_revision"],
                    "maturity": row["maturity"],
                    "score": score,
                }
            )
        tools.sort(key=lambda row: (-row["score"], row["tool_key"]))
        tools = tools[:limit_tools]

    knowledge_states = _knowledge_states(connection, query, tokens, limit=limit_knowledge)
    branch_payload = [branch_index[key] for key in resolved]
    meta = _project_meta(connection)
    fixed_sources = {
        "Devos/project.json",
        "Devos/governance-lock.json",
        "Devos/branches.jsonl",
        "Devos/tasks.jsonl",
        "Devos/task-events.jsonl",
        "Devos/tools.jsonl",
    }
    sources = _source_manifest(connection, fixed_sources | selected_paths)
    packet: dict[str, object] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "scope_key": meta.get("scope_key"),
        "repository": meta.get("repository"),
        "project_name": meta.get("project_name"),
        "query": query,
        "requested_branches": requested,
        "resolved_branches": resolved,
        "projection": {
            "digest": _projection_digest(connection),
            **projection_freshness(connection, host_root),
        },
        "limits": {
            "documents": limit_documents,
            "tasks": limit_tasks,
            "tools": limit_tools,
            "knowledge": limit_knowledge,
            "max_document_chars": max_document_chars,
        },
        "context": {
            "branches": branch_payload,
            "documents": documents,
            "tasks": tasks,
            "tools": tools,
            "knowledge_states": knowledge_states,
        },
        "source_manifest": sources,
        "document_chars_used": max_document_chars - chars_left,
    }
    packet["packet_hash"] = _hash(packet)
    return packet


def status_payload(connection: sqlite3.Connection, host_root: Path) -> dict[str, object]:
    meta = _project_meta(connection)
    return {
        "scope_key": meta.get("scope_key"),
        "repository": meta.get("repository"),
        "project_name": meta.get("project_name"),
        "projection_digest": _projection_digest(connection),
        "freshness": projection_freshness(connection, host_root),
        "counts": {
            "branches": connection.execute("SELECT count(*) FROM branch_state").fetchone()[0],
            "tasks": connection.execute("SELECT count(*) FROM devos_tasks").fetchone()[0],
            "tools": connection.execute("SELECT count(*) FROM tool_registry").fetchone()[0],
            "documents": connection.execute("SELECT count(*) FROM documents").fetchone()[0],
            "knowledge_subjects": connection.execute("SELECT count(*) FROM knowledge_subjects").fetchone()[0],
            "knowledge_transitions": connection.execute("SELECT count(*) FROM knowledge_state_transitions").fetchone()[0],
        },
        "database": runtime_health(connection),
    }


def _default_db(devos_root: Path) -> Path:
    return devos_root / "state" / DEFAULT_DB_NAME


def _open(devos_root: Path, host_root: Path, db_path: Path, refresh: bool) -> sqlite3.Connection:
    if refresh or not db_path.exists():
        build(devos_root, host_root, db_path)
    return connect_runtime(db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--refresh", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    packet = sub.add_parser("packet")
    packet.add_argument("query")
    packet.add_argument("--branch", action="append", required=True, dest="branches")
    packet.add_argument("--limit-documents", type=int, default=6)
    packet.add_argument("--limit-tasks", type=int, default=6)
    packet.add_argument("--limit-tools", type=int, default=4)
    packet.add_argument("--limit-knowledge", type=int, default=6)
    packet.add_argument("--max-document-chars", type=int, default=6000)

    expand = sub.add_parser("expand-knowledge")
    expand.add_argument("subject_id")

    args = parser.parse_args()
    devos_root = args.devos_root.resolve()
    host_root = (args.host_root or devos_root.parent).resolve()
    db_path = (args.db or _default_db(devos_root)).resolve()
    connection: sqlite3.Connection | None = None
    try:
        connection = _open(devos_root, host_root, db_path, args.refresh)
        if args.command == "status":
            result = {"ok": True, **status_payload(connection, host_root)}
        elif args.command == "expand-knowledge":
            result = {"ok": True, "knowledge": expand_knowledge_state(connection, subject_id=args.subject_id)}
        else:
            result = {
                "ok": True,
                "packet": build_packet(
                    connection,
                    host_root,
                    args.query,
                    args.branches,
                    limit_documents=args.limit_documents,
                    limit_tasks=args.limit_tasks,
                    limit_tools=args.limit_tools,
                    limit_knowledge=args.limit_knowledge,
                    max_document_chars=args.max_document_chars,
                ),
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
