#!/usr/bin/env python3
"""Portable SQLite runtime policy for DevOS.

The database is generated host state. Projection tables are rebuildable from
checked-in repository inputs while runtime_kv is preserved across normal builds.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

CURRENT_SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
MIGRATION_1_SIGNATURE = "devos-runtime-db-v1:projection+fts+runtime-kv"

SCHEMA_V1 = r'''
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    signature TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS build_manifest (
    source_path TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    UNIQUE(path, section)
);
CREATE TABLE IF NOT EXISTS branch_state (
    branch_key TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    surfaces_json TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devos_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    task_type TEXT NOT NULL,
    owner_role TEXT NOT NULL,
    assigned_agent TEXT,
    objective TEXT NOT NULL,
    transfer_canary INTEGER NOT NULL,
    tracking_json TEXT NOT NULL,
    acceptance_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_branches (
    task_id TEXT NOT NULL,
    branch_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(task_id, branch_key),
    FOREIGN KEY(task_id) REFERENCES devos_tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(branch_key) REFERENCES branch_state(branch_key) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(task_id, depends_on_task_id),
    FOREIGN KEY(task_id) REFERENCES devos_tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(depends_on_task_id) REFERENCES devos_tasks(task_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_key TEXT PRIMARY KEY,
    repository TEXT NOT NULL DEFAULT '',
    verified_revision TEXT NOT NULL DEFAULT '',
    maturity TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_kv (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_branch_status ON branch_state(status);
CREATE INDEX IF NOT EXISTS idx_tasks_ready ON devos_tasks(status, priority, task_id);
CREATE INDEX IF NOT EXISTS idx_task_branches_branch ON task_branches(branch_key, task_id);
'''


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (table,)
    ).fetchone() is not None


def _ensure_fts(connection: sqlite3.Connection) -> bool:
    if _table_exists(connection, "documents_fts"):
        return True
    try:
        connection.executescript(r'''
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            path, title, section, content,
            content='documents', content_rowid='id'
        );
        CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, path, title, section, content)
            VALUES (new.id, new.path, new.title, new.section, new.content);
        END;
        CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, path, title, section, content)
            VALUES ('delete', old.id, old.path, old.title, old.section, old.content);
        END;
        CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, path, title, section, content)
            VALUES ('delete', old.id, old.path, old.title, old.section, old.content);
            INSERT INTO documents_fts(rowid, path, title, section, content)
            VALUES (new.id, new.path, new.title, new.section, new.content);
        END;
        ''')
        return True
    except sqlite3.OperationalError as exc:
        if "fts5" not in str(exc).lower():
            raise
        return False


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_V1)
    _ensure_fts(connection)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, signature) VALUES (?, ?)",
        (CURRENT_SCHEMA_VERSION, MIGRATION_1_SIGNATURE),
    )
    connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    connection.commit()


def connect_runtime(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    ensure_schema(connection)
    return connection


def runtime_health(connection: sqlite3.Connection) -> dict[str, object]:
    return {
        "schema_version": connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] or 0,
        "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
        "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
        "foreign_keys": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
        "busy_timeout_ms": connection.execute("PRAGMA busy_timeout").fetchone()[0],
        "fts5": _table_exists(connection, "documents_fts"),
        "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
    }


def cleanup_runtime_files(path: Path) -> None:
    path = Path(path)
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
