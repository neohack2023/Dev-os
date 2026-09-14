# AGI_MEMORY_RUNTIME_MATERIALIZATION_01

Status: VALIDATED CANDIDATE RUNTIME MATERIALIZATION
Authority effect: NONE
Promotion state: CANDIDATE_ONLY

## Scope

This checkpoint records deterministic runtime evidence that the merged `AGI_MEMORY_DELIVERY_FITNESS_01` research and candidate pack can be materialized through the portable DevOS runtime without committing generated SQLite state.

Baseline repository authority:

- repository: `neohack2023/Dev-os`
- merged main baseline: `f576a39d46190956a235bc967bda2e21dfc63797`
- candidate validation revision: `8532f1300a1d22ac112631e95f76864e8e1bbca7`

The standalone DevOS repository is a portable distribution and intentionally ships without host-owned `project.json`, task state, receipts, or runtime DB. The validation therefore copies the merged package into an isolated temporary host, initializes that host with the package's own `init_instance()` path, and builds the generated DB there.

## Deterministic procedure

1. Copy the exact candidate DevOS package into a temporary host.
2. Initialize the host with:
   - scope: `devos-self`
   - repository: `neohack2023/Dev-os`
   - project name: `DevOS`
3. Build a fresh generated knowledge DB from the repository projection.
4. Query the projection for `delivered` and require the merged research packet to be returned.
5. Ingest `Devos/knowledge/agi-memory-delivery-fitness-01.json` through `candidate_ingest.py`.
6. Verify candidate-only evidence, reflection, procedure, experience, capability, and lifecycle records are materialized.
7. Verify the capability IDs emitted by ingestion exist in `learning_capabilities`.
8. Verify DB health and schema identity.

## Observed runtime evidence

Observed in GitHub Actions validation run `34877620852` on candidate revision `8532f1300a1d22ac112631e95f76864e8e1bbca7` before this checkpoint file was added.

- pack id: `STONE-20260914-DEVOS-AGI-MEMORY-DELIVERY-01`
- branch: `project-core`
- authority effect: `NONE`
- promotion state: `CANDIDATE_ONLY`
- maturity stages: `RECOGNITION`, `RECOGNITION`
- validated for transfer: `false`, `false`
- delivered-context-fitness capability: `capability:5e1507fe0e44a3d8755a6aab`
- structural-metadata-over-advisory capability: `capability:449ea817129c6ac4f2a77d52`
- query returned:
  - `Devos/research/AGI_MEMORY_DELIVERY_FITNESS_01.md`
  - `Devos/checkpoints/AGI_MEMORY_DELIVERY_FITNESS_01.md`
- runtime counts:
  - evidence roots: 5
  - atomic findings: 5
  - evidence delta packets: 2
  - reflection candidates: 2
  - learning experiences: 2
  - learning procedures: 2
  - learning capabilities: 2
  - learning capability events: 2
- DB health:
  - integrity check: `ok`
  - FTS5: enabled
  - foreign keys: enabled
  - journal mode: WAL
  - schema version: 9
  - user version: 9
- pre-checkpoint projection digest: `1c6297c6c1bb9ef9916eccead5c4d041d9c1d6ee8ea479ca3db3ed901865f449`

The projection digest is recorded as evidence for the pre-checkpoint candidate revision only. Adding this Markdown checkpoint legitimately changes the repository projection and may therefore change the digest on the next rebuild.

## Validation

At candidate revision `8532f1300a1d22ac112631e95f76864e8e1bbca7`:

- portable validation: PASS
- retrieval ablation benchmark: PASS
- GitHub authority validation: PASS
- GitHub policy validation: PASS
- unit tests: 106/106 PASS

The end-to-end materialization test is `test_agi_memory_pack_materializes_from_repository_projection_and_queries_back` in `Devos/tests/test_candidate_ingest.py`.

## Negative evidence / corrected approaches

### Direct build from the portable distribution

Initial attempt treated the standalone DevOS repository as if it were already a host instance. It failed because `Devos/project.json` was correctly absent.

Classification: stale host-state assumption.

Resolution: initialize an isolated temporary host using the package's supported `init_instance()` path before building the DB. The portable distribution remains clean and host-neutral.

### Capability-key persistence assumption

A second attempt assumed `learning_capabilities.payload_json` persisted `capability_key`. It does not. The key participates in stable capability ID derivation, while the stored `CapabilityRecord` contains the resulting identity and capability state.

Classification: test-contract mismatch.

Resolution: bind the ingestion entry IDs to the capability IDs emitted by `ingest_pack()` and verify those exact IDs exist in the durable runtime table.

## Governance interpretation

This slice proves repository projection, retrieval, candidate ingestion, lineage materialization, and runtime DB health. It does not prove transfer or authorize promotion.

Both candidate capabilities remain at `RECOGNITION`, are not validated for transfer, retain `authority_effect: NONE`, and remain `CANDIDATE_ONLY`.

Generated SQLite state remains runtime-owned and uncommitted.

## Remaining gap

The next bounded learning slice is held-out delivery-fitness evaluation for `devos.context.delivery_fitness` and structural-vs-advisory metadata evaluation for `devos.metadata.structural_capture`. T2/T3 evidence must be added separately before either capability can advance beyond recognition.
