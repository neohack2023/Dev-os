# KNOWLEDGE_RUNTIME_PORT_01

Status: candidate until exact-head CI is green and promoted to `main`.

## Objective

Neutralize Project Orath's `knowledge_runtime.py` into a host-independent retrieval layer for the portable DevOS SQLite substrate.

## Source lineage

- source repository: `neohack2023/project-orath`
- source executable: `tools/knowledge_runtime.py`
- source blob: `eeaf9fcfaf611696f15ebd02a72ad55e36e43aca`

The Orath implementation's governance-claim ranking, feedback persistence, and improvement-candidate promotion were intentionally not copied because Portable DevOS v0.4.0 does not yet own those database tables or authority classes.

## Portable deliverables

- `runtime/knowledge_runtime.py`
- `schemas/context-packet.schema.json`
- `contracts/KNOWLEDGE_RUNTIME.md`
- `tests/test_knowledge_runtime.py`
- package and CI integration

## Behavior

The runtime emits deterministic context packets from the generated SQLite projection. Packets contain project identity, requested and dependency-resolved branches, query-ranked document excerpts, effective task state, relevant tools, source hashes, projection freshness, bounded limits, and a deterministic packet hash.

Direct branch ownership is a ranking signal only after query relevance is established. Irrelevant direct-scope documents are never promoted over relevant dependency-scope evidence.

Existing stale projections are reported but not silently rebuilt. Explicit `--refresh` is required to replace stale generated state.

## Acceptance gates

1. branch dependencies resolve deterministically;
2. unknown branches fail closed;
3. direct-scope relevant material ranks before dependency-scope material;
4. effective task lifecycle state is preserved in packets;
5. tool selection is query-scored and bounded;
6. aggregate document excerpts obey the hard character budget;
7. packet hashes are deterministic for identical inputs and projection state;
8. source provenance is bound into the packet;
9. stale source files are surfaced without implicit refresh;
10. full DevOS tests and public CLI packet generation pass in CI.
