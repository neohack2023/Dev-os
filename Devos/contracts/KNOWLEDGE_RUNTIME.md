# Knowledge Runtime Contract

The portable knowledge runtime converts the generated SQLite projection into bounded, branch-aware context packets for agents.

## Inputs

A context packet requires:

- a non-empty retrieval query;
- one or more registered branch keys;
- a materialized DevOS knowledge database.

If the database does not exist, the CLI may build generated state from checked-in host sources. A stale existing projection is reported as stale and is not silently refreshed unless `--refresh` is explicitly requested.

## Branch closure

Requested branches are resolved through their declared dependency graph. Dependencies are included before dependents. Unknown branches, missing dependencies, and dependency cycles are errors.

Document and task ranking distinguishes direct requested branches from dependency branches. Direct scope is a relevance/ranking signal, never a substitute for query evidence.

## Retrieval and ranking

Ranking is deterministic and model-free.

Documents are scored from query matches in title, section, path, and content. Irrelevant documents are excluded. Documents owned by directly requested branch surfaces rank before equally relevant dependency-scope documents.

Tasks are selected from the resolved branch closure. Query matches in title, objective, acceptance criteria, tracking, and evidence improve rank; direct-branch tasks precede dependency-only tasks. Effective task state already includes lifecycle-event overlays from the task queue projection.

Tools are included only when the query matches their registered identity or metadata. Full raw tool payloads are not emitted into packets.

## Bounds

The runtime enforces hard upper limits on document count, task count, tool count, and aggregate document excerpt characters. Individual document excerpts are clipped deterministically around the earliest query token.

## Provenance

Each packet carries:

- project scope and repository identity;
- the knowledge projection digest;
- projection freshness and changed-source paths;
- the resolved branch closure;
- source manifest entries with SHA-256 hashes;
- a deterministic packet SHA-256 hash.

The packet is a retrieval product, not a new authority source. Its contents inherit authority from the checked-in sources represented by the projection.

## Mutation boundary

Packet generation is read-only with respect to existing repository and database state. Missing generated state may be built. Stale generated state is not refreshed implicitly. `--refresh` is the explicit rebuild boundary.
