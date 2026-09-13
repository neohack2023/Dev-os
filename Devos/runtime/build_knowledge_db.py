#!/usr/bin/env python3
"""Build and query the portable DevOS SQLite knowledge projection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

try:
    from .db_runtime import cleanup_runtime_files, connect_runtime, runtime_health
    from .task_queue import load_tasks
except ImportError:
    from db_runtime import cleanup_runtime_files, connect_runtime, runtime_health
    try:
        from task_queue import load_tasks
    except ImportError:
        load_tasks = None

DEVOS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_NAME = "devos-knowledge.db"
PROJECTION_TABLES = (
    "task_dependencies", "task_branches", "devos_tasks", "tool_registry",
    "branch_state", "documents", "build_manifest", "project_meta", "projection_meta",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: object) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path} line {line_no}: expected JSON object")
        rows.append(value)
    return rows


def _first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _markdown_sections(text: str) -> Iterable[tuple[str, str]]:
    section = ""
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith("## "):
            if buf and any(item.strip() for item in buf):
                yield section, "\n".join(buf).strip()
            section = line.lstrip("#").strip()
            buf = [line]
        else:
            buf.append(line)
    if buf and any(item.strip() for item in buf):
        yield section, "\n".join(buf).strip()


def iter_markdown_files(host_root: Path, devos_root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for name in ("README.md", "ARCHITECTURE.md", "AGENTS.md"):
        path = host_root / name
        if path.is_file():
            seen.add(path.resolve())
            yield path
    docs = host_root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md")):
            if path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                yield path
    if devos_root.is_dir():
        for path in sorted(devos_root.rglob("*.md")):
            rel = path.relative_to(devos_root)
            if rel.parts and rel.parts[0] in {"state", "receipts"}:
                continue
            if len(rel.parts) >= 2 and rel.parts[:2] == ("tests", "fixtures"):
                continue
            if path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                yield path


def _record_manifest(connection: sqlite3.Connection, host_root: Path, path: Path, kind: str) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO build_manifest(source_path, source_kind, source_hash) VALUES (?, ?, ?)",
        (path.relative_to(host_root).as_posix(), kind, sha256_bytes(path.read_bytes())),
    )


def _insert_documents(connection: sqlite3.Connection, host_root: Path, devos_root: Path) -> int:
    count = 0
    for path in iter_markdown_files(host_root, devos_root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(host_root).as_posix()
        title = _first_heading(text, path.stem)
        kind = "devos" if path.is_relative_to(devos_root) else ("root" if path.parent == host_root else "documentation")
        for section, content in _markdown_sections(text):
            connection.execute(
                "INSERT INTO documents(path,title,section,content,content_hash,kind) VALUES (?,?,?,?,?,?)",
                (relative, title, section, content, sha256_bytes(content.encode("utf-8")), kind),
            )
            count += 1
        _record_manifest(connection, host_root, path, "markdown")
    return count


def _insert_project(connection: sqlite3.Connection, host_root: Path, devos_root: Path) -> dict:
    project_path = devos_root / "project.json"
    governance_path = devos_root / "governance-lock.json"
    project = _read_json(project_path)
    governance = _read_json(governance_path)
    for key in ("project_name", "scope_key", "repository", "devos_version"):
        if not project.get(key):
            raise ValueError(f"project.json missing {key}")
    if governance.get("scope_key") != project["scope_key"] or governance.get("repository") != project["repository"]:
        raise ValueError("governance-lock identity must match project.json")
    meta = {
        "project_name": project["project_name"],
        "scope_key": project["scope_key"],
        "repository": project["repository"],
        "devos_version": project["devos_version"],
        "repository_execution_authority": (project.get("authority") or {}).get("repository_execution", "github"),
        "external_memory_authority": (project.get("authority") or {}).get("external_memory", "configured-by-host"),
    }
    connection.executemany("INSERT INTO project_meta(key,value) VALUES (?,?)", sorted((k, str(v)) for k, v in meta.items()))
    _record_manifest(connection, host_root, project_path, "project")
    _record_manifest(connection, host_root, governance_path, "governance")
    return project


def _insert_branches(connection: sqlite3.Connection, host_root: Path, devos_root: Path, scope: str) -> int:
    path = devos_root / "branches.jsonl"
    rows = _load_jsonl(path)
    seen: set[str] = set()
    for row in rows:
        key = row.get("branch_key")
        if not isinstance(key, str) or not key:
            raise ValueError("branch row missing branch_key")
        if key in seen:
            raise ValueError(f"duplicate branch key: {key}")
        seen.add(key)
        if row.get("scope_key") != scope:
            raise ValueError(f"{key}: branch scope does not match project scope")
        connection.execute(
            "INSERT INTO branch_state(branch_key,scope_key,title,status,dependencies_json,surfaces_json,row_hash) VALUES (?,?,?,?,?,?,?)",
            (key, scope, row.get("title", key), row.get("status", ""), json.dumps(row.get("dependencies", []), sort_keys=True), json.dumps(row.get("surfaces", []), sort_keys=True), canonical_hash(row)),
        )
    _record_manifest(connection, host_root, path, "branches")
    return len(rows)


def _load_effective_tasks(devos_root: Path) -> list[dict]:
    if load_tasks is None:
        return _load_jsonl(devos_root / "tasks.jsonl")
    return load_tasks(devos_root / "tasks.jsonl", devos_root / "task-events.jsonl", devos_root / "branches.jsonl")


def _insert_tasks(connection: sqlite3.Connection, host_root: Path, devos_root: Path) -> int:
    tasks = _load_effective_tasks(devos_root)
    ids = {row["task_id"] for row in tasks}
    for row in tasks:
        acceptance = row.get("acceptance_criteria", row.get("acceptance", []))
        dependencies = row.get("dependencies", row.get("depends_on", []))
        connection.execute(
            "INSERT INTO devos_tasks(task_id,title,priority,status,task_type,owner_role,assigned_agent,objective,transfer_canary,tracking_json,acceptance_json,evidence_refs_json,manifest_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["task_id"], row["title"], row["priority"], row["status"], row["task_type"], row["owner_role"], row.get("assigned_agent"), row["objective"], int(bool(row.get("transfer_canary"))), json.dumps(row.get("tracking", []), sort_keys=True), json.dumps(acceptance, sort_keys=True), json.dumps(row.get("evidence_refs", []), sort_keys=True), canonical_hash(row)),
        )
        for ordinal, branch_key in enumerate(row.get("branch_keys", [])):
            connection.execute("INSERT INTO task_branches(task_id,branch_key,ordinal) VALUES (?,?,?)", (row["task_id"], branch_key, ordinal))
        for ordinal, dep in enumerate(dependencies):
            if dep not in ids:
                raise ValueError(f"{row['task_id']}: unknown dependency {dep}")
            connection.execute("INSERT INTO task_dependencies(task_id,depends_on_task_id,ordinal) VALUES (?,?,?)", (row["task_id"], dep, ordinal))
    for name, kind in (("tasks.jsonl", "tasks"), ("task-events.jsonl", "task-events")):
        path = devos_root / name
        if path.exists():
            _record_manifest(connection, host_root, path, kind)
    return len(tasks)


def _insert_tools(connection: sqlite3.Connection, host_root: Path, devos_root: Path) -> int:
    path = devos_root / "tools.jsonl"
    rows = _load_jsonl(path)
    for row in rows:
        key = row.get("tool_key")
        if not isinstance(key, str) or not key:
            raise ValueError("tool row missing tool_key")
        connection.execute(
            "INSERT INTO tool_registry(tool_key,repository,verified_revision,maturity,payload_json,row_hash) VALUES (?,?,?,?,?,?)",
            (key, str(row.get("repository", "")), str(row.get("verified_revision", "")), str(row.get("maturity", "")), json.dumps(row, sort_keys=True), canonical_hash(row)),
        )
    if path.exists():
        _record_manifest(connection, host_root, path, "tools")
    return len(rows)


def _projection_digest(connection: sqlite3.Connection) -> str:
    payload: dict[str, object] = {}
    for table, order in (
        ("project_meta", "key"), ("build_manifest", "source_path"), ("branch_state", "branch_key"),
        ("devos_tasks", "task_id"), ("task_branches", "task_id, ordinal"),
        ("task_dependencies", "task_id, ordinal"), ("tool_registry", "tool_key"),
        ("documents", "path, section"),
    ):
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        payload[table] = [dict(row) for row in rows]
    return canonical_hash(payload)


def reset_projection(connection: sqlite3.Connection) -> None:
    for table in PROJECTION_TABLES:
        connection.execute(f"DELETE FROM {table}")


def build(devos_root: Path, host_root: Path, db_path: Path, fresh: bool = False) -> dict[str, object]:
    devos_root, host_root, db_path = Path(devos_root).resolve(), Path(host_root).resolve(), Path(db_path).resolve()
    if fresh:
        cleanup_runtime_files(db_path)
    connection = connect_runtime(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        reset_projection(connection)
        project = _insert_project(connection, host_root, devos_root)
        branches = _insert_branches(connection, host_root, devos_root, str(project["scope_key"]))
        tasks = _insert_tasks(connection, host_root, devos_root)
        tools = _insert_tools(connection, host_root, devos_root)
        documents = _insert_documents(connection, host_root, devos_root)
        digest = _projection_digest(connection)
        meta = {
            "projection_digest": digest,
            "documents": str(documents),
            "branches": str(branches),
            "tasks": str(tasks),
            "tools": str(tools),
        }
        connection.executemany("INSERT INTO projection_meta(key,value) VALUES (?,?)", sorted(meta.items()))
        connection.commit()
        return {"ok": True, "db": str(db_path), "projection_digest": digest, "documents": documents, "branches": branches, "tasks": tasks, "tools": tools}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def query(db_path: Path, term: str, limit: int = 10) -> list[dict[str, object]]:
    connection = connect_runtime(Path(db_path))
    try:
        fts = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents_fts'").fetchone()
        if fts:
            rows = connection.execute(
                "SELECT d.path,d.title,d.section,d.kind,d.content FROM documents_fts f JOIN documents d ON d.id=f.rowid WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts), d.path, d.section LIMIT ?",
                (term, limit),
            ).fetchall()
        else:
            like = f"%{term}%"
            rows = connection.execute(
                "SELECT path,title,section,kind,content FROM documents WHERE content LIKE ? OR title LIKE ? OR section LIKE ? ORDER BY path,section LIMIT ?",
                (like, like, like, limit),
            ).fetchall()
        return [{"path": row["path"], "title": row["title"], "section": row["section"], "kind": row["kind"], "excerpt": row["content"][:240]} for row in rows]
    finally:
        connection.close()


def health(db_path: Path) -> dict[str, object]:
    connection = connect_runtime(Path(db_path))
    try:
        result = runtime_health(connection)
        result["projection_digest"] = (connection.execute("SELECT value FROM projection_meta WHERE key='projection_digest'").fetchone() or [None])[0]
        result["runtime_kv_count"] = connection.execute("SELECT count(*) FROM runtime_kv").fetchone()[0]
        return result
    finally:
        connection.close()


def _default_db(devos_root: Path) -> Path:
    return Path(devos_root) / "state" / DEFAULT_DB_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--db", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build")
    p_build.add_argument("--fresh", action="store_true")
    p_query = sub.add_parser("query")
    p_query.add_argument("term")
    p_query.add_argument("--limit", type=int, default=10)
    sub.add_parser("health")
    args = parser.parse_args()
    devos_root = args.devos_root.resolve()
    host_root = (args.host_root or devos_root.parent).resolve()
    db_path = (args.db or _default_db(devos_root)).resolve()
    try:
        if args.command == "build":
            result = build(devos_root, host_root, db_path, args.fresh)
        elif args.command == "query":
            result = {"ok": True, "results": query(db_path, args.term, args.limit)}
        else:
            result = {"ok": True, **health(db_path)}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
