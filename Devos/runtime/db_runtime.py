#!/usr/bin/env python3
"""Portable SQLite runtime policy and migrations for DevOS."""
from __future__ import annotations
from pathlib import Path
import sqlite3
DEVOS_ROOT=Path(__file__).resolve().parents[1]
BASE_SCHEMA=DEVOS_ROOT/"schemas"/"runtime-db-v1.sql"
MIGRATION_2=DEVOS_ROOT/"schemas"/"runtime-db-v2.sql"
MIGRATION_3=DEVOS_ROOT/"schemas"/"runtime-db-v3.sql"
MIGRATION_4=DEVOS_ROOT/"schemas"/"runtime-db-v4.sql"
MIGRATION_5=DEVOS_ROOT/"schemas"/"runtime-db-v5.sql"
MIGRATION_6=DEVOS_ROOT/"schemas"/"runtime-db-v6.sql"
CURRENT_SCHEMA_VERSION=6
BUSY_TIMEOUT_MS=5000
MIGRATION_1_SIGNATURE="devos-runtime-db-v1:projection+fts+runtime-kv"
MIGRATION_2_SIGNATURE="devos-runtime-db-v2:evidence-roots+findings+triangulation+deltas"
MIGRATION_3_SIGNATURE="devos-runtime-db-v3:reflection-candidates"
MIGRATION_4_SIGNATURE="devos-runtime-db-v4:learning-procedures+evaluations+experiences+capability-events"
MIGRATION_5_SIGNATURE="devos-runtime-db-v5:promotion-envelopes+verification-decisions"
MIGRATION_6_SIGNATURE="devos-runtime-db-v6:mason-execution-plans+immutable-receipts"
def _table_exists(connection,table): return connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",(table,)).fetchone() is not None
def _ensure_fts(connection):
    if _table_exists(connection,"documents_fts"): return True
    try:
        connection.executescript("""
        CREATE VIRTUAL TABLE documents_fts USING fts5(path,title,section,content,content='documents',content_rowid='id');
        CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN INSERT INTO documents_fts(rowid,path,title,section,content) VALUES(new.id,new.path,new.title,new.section,new.content); END;
        CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN INSERT INTO documents_fts(documents_fts,rowid,path,title,section,content) VALUES('delete',old.id,old.path,old.title,old.section,old.content); END;
        CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN INSERT INTO documents_fts(documents_fts,rowid,path,title,section,content) VALUES('delete',old.id,old.path,old.title,old.section,old.content); INSERT INTO documents_fts(rowid,path,title,section,content) VALUES(new.id,new.path,new.title,new.section,new.content); END;
        """); return True
    except sqlite3.OperationalError as exc:
        if "fts5" not in str(exc).lower(): raise
        return False
def _record_migration(connection,version,signature):
    row=connection.execute("SELECT signature FROM schema_migrations WHERE version=?",(version,)).fetchone()
    if row is not None and row[0]!=signature: raise sqlite3.DatabaseError(f"schema migration signature mismatch at version {version}")
    connection.execute("INSERT OR IGNORE INTO schema_migrations(version,signature) VALUES (?,?)",(version,signature))
def ensure_schema(connection):
    connection.executescript(BASE_SCHEMA.read_text()); _ensure_fts(connection); _record_migration(connection,1,MIGRATION_1_SIGNATURE)
    connection.executescript(MIGRATION_2.read_text()); _record_migration(connection,2,MIGRATION_2_SIGNATURE)
    connection.executescript(MIGRATION_3.read_text()); _record_migration(connection,3,MIGRATION_3_SIGNATURE)
    connection.executescript(MIGRATION_4.read_text()); _record_migration(connection,4,MIGRATION_4_SIGNATURE)
    connection.executescript(MIGRATION_5.read_text()); _record_migration(connection,5,MIGRATION_5_SIGNATURE)
    connection.executescript(MIGRATION_6.read_text()); _record_migration(connection,6,MIGRATION_6_SIGNATURE)
    connection.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION}"); connection.commit()
def connect_runtime(path:Path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(path); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}"); c.execute("PRAGMA journal_mode=WAL"); ensure_schema(c); return c
def runtime_health(connection):
    return {"schema_version":connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] or 0,"user_version":connection.execute("PRAGMA user_version").fetchone()[0],"journal_mode":connection.execute("PRAGMA journal_mode").fetchone()[0],"foreign_keys":bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),"busy_timeout_ms":connection.execute("PRAGMA busy_timeout").fetchone()[0],"fts5":_table_exists(connection,"documents_fts"),"integrity_check":connection.execute("PRAGMA integrity_check").fetchone()[0]}
def cleanup_runtime_files(path:Path):
    for candidate in (Path(path),Path(str(path)+"-wal"),Path(str(path)+"-shm")):
        try:candidate.unlink()
        except FileNotFoundError:pass
