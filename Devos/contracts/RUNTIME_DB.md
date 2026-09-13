# Runtime Database Contract

DevOS may materialize checked-in repository knowledge into a local SQLite database for fast deterministic retrieval. The database is a generated projection/cache, never a new authority source.

## Default location

The portable default is `Devos/state/devos-knowledge.db`. Hosts may override the path. Database files, WAL/SHM sidecars, caches, and other generated runtime material stay outside distribution canon.

## Projection boundary

Normal rebuilds replace only projection-owned tables derived from checked-in inputs: project/governance identity, Markdown documents, branch state, effective task state, task edges, tool registry rows, provenance manifest, and projection metadata.

Runtime-owned tables are preserved across normal rebuilds. `runtime_kv` is the initial durable runtime-state surface for later reflection/learning slices. `--fresh` is the explicit destructive reset and may remove runtime-owned state.

## Determinism and provenance

Every materialized source receives a repository-relative path and SHA-256 in `build_manifest`. Canonical row hashing and `projection_digest` provide a logical determinism check across rebuilds without pretending SQLite file bytes or WAL layout are canonical.

The database must preserve the authority separation declared by `project.json` and `governance-lock.json`. Building or querying the DB cannot promote evidence, change governance, authorize work, or replace GitHub as repository execution truth.

## SQLite policy

`runtime/db_runtime.py` owns connection policy and migrations. Version 1 is defined in `schemas/runtime-db-v1.sql` with foreign keys enabled, WAL journaling, a bounded busy timeout, integrity checks, and FTS5 document search when the host SQLite build supports it. If FTS5 is unavailable, document queries fall back to deterministic `LIKE` search.

## Commands

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py query "search terms"
python Devos/runtime/build_knowledge_db.py health
python Devos/runtime/build_knowledge_db.py build --fresh
```

Builders must be reproducible from checked-in sources, preserve provenance and authority fields, pass integrity checks, and never silently erase runtime-owned state.
