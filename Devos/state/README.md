# Runtime state

Generated local databases, caches, and other rebuildable DevOS runtime material belong here or in a host-configured generated path. Distribution defaults must not contain another project's runtime state.

`KNOWLEDGE_DB_PORT_01` adds the default generated database path `Devos/state/devos-knowledge.db`. The DB is a rebuildable repository projection plus explicitly runtime-owned tables. Database files and SQLite WAL/SHM sidecars are ignored by Git and must never be promoted as portable package canon.
