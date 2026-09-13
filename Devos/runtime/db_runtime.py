#!/usr/bin/env python3
"""Portable SQLite runtime policy and migrations for DevOS."""
from __future__ import annotations

from pathlib import Path
import sqlite3

DEVOS_ROOT = Path(__file__).resolve().parents[1]
BASE_SCHEMA = DEVOS_ROOT / "schemas" / "runtime-db-v1.sql"
MIGRATION_2 = DEVOS_ROOT / "schemas" / "runtime-db-v2.sql"
CURRENT_SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 5000
MIGRATION_1_SIGNATURE = "devos-runtime-db-v1:projection+fts+runtime-kv"
MIGRATION_2_SIGNATURE = "devos-runtime-db-v2:evidence-roots+findings+triangulation+deltas"


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


def _record_migration(connection: sqlite3.Connection, version: int, signature: str) -> None:
    row = connection.execute("SELECT signature FROM schema_migrations WHERE version=?", (version,)).fetchone()
    if row is not None and row[0] != signature:
        raise sqlite3.DatabaseError(f"schema migration signature mismatch at version {version}")
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, signature) VALUES (?, ?)",
        (version, signature),
    )


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(BASE_SCHEMA.read_text(encoding="utf-8"))
    _ensure_fts(connection)
    _record_migration(connection, 1, MIGRATION_1_SIGNATURE)
    connection.executescript(MIGRATION_2.read_text(encoding="utf-8"))
    _record_migration(connection, 2, MIGRATION_2_SIGNATURE)
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
