# KNOWLEDGE_DB_PORT_01

Status: checkpoint candidate

## Scope

Neutralize the Project Orath `build_knowledge_db.py` / `db_runtime.py` pair into a host-independent SQLite knowledge substrate under `Devos/runtime/`.

## Portable runtime

- `runtime/db_runtime.py`
  - stdlib SQLite only
  - foreign keys enabled
  - WAL journaling
  - bounded busy timeout
  - schema migration ledger + `PRAGMA user_version`
  - integrity health report
  - FTS5 setup when available
- `runtime/build_knowledge_db.py`
  - deterministic repository projection
  - Markdown section materialization
  - effective DevOS task/event projection
  - branch/task/tool edges
  - provenance manifest with SHA-256
  - canonical logical `projection_digest`
  - query + health CLI
  - normal rebuild preserves runtime-owned state
  - `--fresh` is the explicit destructive reset
- `schemas/runtime-db-v1.sql`
  - inspectable v1 portable base schema

## State boundary

Default generated DB: `Devos/state/devos-knowledge.db`.

Database files and WAL/SHM sidecars are host runtime state and are ignored by Git. The SQLite projection does not become an authority source. GitHub remains repository execution truth; STONE/MASON remain durable promotion gates.

## Portable fixtures

`tests/fixtures/knowledge_db/host/` proves the builder against a generic host repository with project/governance identity, two knowledge branches, append-only task lifecycle overlay, a pinned tool row, and searchable Markdown.

## Acceptance evidence

The test suite must prove:

1. schema migration is idempotent;
2. WAL/foreign-key/busy-timeout policy is active;
3. repository Markdown is queryable;
4. branch/task/tool projections materialize deterministically;
5. lifecycle events alter effective task state without rewriting declarations;
6. task dependency edges are preserved;
7. build inputs are recorded by path + SHA-256;
8. repeated normal rebuilds produce the same logical projection digest;
9. runtime-owned state survives normal rebuilds;
10. `--fresh` removes runtime-owned state;
11. CI builds and queries the fixture DB through the public CLI.

## Origin

- Project Orath `tools/build_knowledge_db.py` source blob: `1f1e8b8bc6cc9cbcf1cf0bb8a574a8dfe09587cf`
- Project Orath `tools/db_runtime.py`: neutralized from the live source implementation inspected during this slice.
- Project Orath base schema lineage: `knowledge/schema.sql` blob `de73b2967a8e682913702bb00fd3ed6f2d57c33c`

Host-specific Orath knowledge, governance claims, Daggerfall documents, `.build/orath-knowledge.db`, fixed branch names, and Project Orath IDs are intentionally excluded.
