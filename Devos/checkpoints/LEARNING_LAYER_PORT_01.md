# LEARNING_LAYER_PORT_01

Status: checkpoint candidate
Target version: DevOS 0.8.0

## Goal

Port a host-independent governed learning layer that converts stored reflection candidates into reusable candidate memory/procedure/capability state while preserving evidence lineage and authority boundaries.

## Source lineage

Neutralized from Project Orath:

- `tools/learning_threshold.py` source blob `c24939c0b9fc6e869a4de290740a6560b11327d0`
- `tools/learning_store.py` source inspected from `project-orath/main`
- `tests/test_learning_threshold.py` source blob `132bf80734fa0661f08c621ce8d36e848d8062d5`
- `tests/test_learning_store.py` source blob `a1303a53a0ac23c5806c2451f2d8a1203b58e96c`

The portable implementation intentionally changes Orath behavior where needed for reproducibility and authority safety.

## Portable behavior

- memory forms: episodic, semantic, procedural, negative
- procedure lineage must resolve to stored reflection candidates
- procedure evidence must be a subset of reflection-grounded evidence
- evaluation tiers T0-T5
- T3 held-out identity must be disjoint from T1/T2 identities
- maturity is capped at TRANSFER in this slice
- T4 and T5 are tracked as regression/canary gates, not higher maturity claims
- learning state is durable runtime state
- exact replay is idempotent
- capability history grows only for changed learning state
- all outputs retain `authority_effect: NONE` and `promotion_state: CANDIDATE_ONLY`

## SQLite

Schema v4 adds:

- `learning_procedures`
- `procedure_reflections`
- `learning_evaluations`
- `evaluation_procedures`
- `learning_experiences`
- `experience_reflections`
- `learning_capabilities`
- `learning_capability_events`

Durable learning tables do not foreign-key rebuildable projection tables.

## Research guidance applied

2026 agent-memory evaluations increasingly measure memory by downstream action/transfer rather than passive recall. MemGym isolates memory effects across realistic agentic regimes; Mem2ActBench tests whether memory changes tool-based behavior; procedural-memory evaluations report local improvement can fail to transfer. The portable layer therefore treats held-out transfer and regression as explicit gates rather than assuming persistence equals learning.

## Acceptance gates

- schema migration is idempotent
- prior evidence/reflection tests remain green under schema v4
- invented learning evidence is rejected
- held-out identity leakage is rejected
- failed T3 caps maturity below TRANSFER
- exact replay does not create duplicate lifecycle events
- normal knowledge projection rebuild preserves learning state
- package validation, full tests, and public learning CLI pass in GitHub Actions

## Authority

This checkpoint introduces candidate learning state only. It grants no authority mutation and no automatic promotion path.
