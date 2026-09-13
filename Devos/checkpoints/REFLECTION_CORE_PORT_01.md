# REFLECTION_CORE_PORT_01

Status: COMPLETE

Portable release: DevOS 0.7.0

## Source lineage

Source repository: `neohack2023/project-orath`

- `tools/reflection_core.py` source blob: `aa3d6a8c33b05d16a607f478057aad5a8f6e8e36`
- `tools/delta_reflection.py` source blob: `4336509373b29cdbcca76f1381d3afdef48f8c07`

The portable implementation keeps the source's strongest laws: deterministic hypothesis identity, explicit alternatives, required disconfirmation, source provenance, `authority_effect: NONE`, and `CANDIDATE_ONLY`.

## Portable additions

- `runtime/reflection_core.py`
- `runtime/delta_reflection.py`
- `runtime/reflection_store.py`
- `schemas/runtime-db-v3.sql`
- `schemas/reflection-request.schema.json`
- `tests/test_reflection_core.py`
- `tests/fixtures/reflection/request-lantern.json`

## Neutralization

Removed Orath naming and branch assumptions.

The first portable adapter consumes the generic evidence delta emitted by `EVIDENCE_RUNTIME_PORT_01`; CI-failure-specific reflection remains a separate future adapter.

Reflection persistence is immutable/idempotent and uses the source delta timestamp rather than wall-clock generation time.

## Research-informed hardening

The slice was reviewed against agent-reflection literature and current production guidance.

The key hardening decision is that reflective prose cannot manufacture supporting evidence. Supporting/opposing references must already be present on the source evidence delta, and every candidate must carry an alternative explanation plus a disconfirmation test.

This preserves the useful evaluator/refinement pattern while reducing the risk that an incorrect self-diagnosis becomes durable pseudo-truth.

## Validation

The slice is accepted only when:

- deterministic reflection identity passes,
- ungrounded evidence references are rejected,
- missing competing explanations are rejected,
- competing hypotheses remain distinct,
- identical replay is idempotent,
- unknown branches are rejected at admission,
- normal projection rebuild preserves reflection candidates,
- schema v3 migration is healthy,
- the public CLI derives and lists a reflection from an admitted evidence fixture,
- the complete DevOS CI workflow is green.

## Authority boundary

Reflection is a candidate generator, not an authority surface.

The executable chain after this checkpoint is:

`repo truth -> knowledge projection -> evidence episode -> evidence delta -> reflection candidate`

Promotion remains outside this slice and must continue through governed evidence/evaluation plus STONE -> MASON.
