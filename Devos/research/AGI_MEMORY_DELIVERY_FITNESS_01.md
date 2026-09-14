# AGI_MEMORY_DELIVERY_FITNESS_01

Status: **CANDIDATE / RESEARCH-BACKED / AUTHORITY_EFFECT_NONE**

Observed: 2026-09-14

DevOS base revision: `4357d080043e0db56a919d3887dc2f10a833603d` (`0.13.0`)

External repositories inspected:

- `kdbhalala/agi-memory` at `3c93e9e52b4038578501e2bbe4c374476d6db34f`
- `adecubed/adebench` at `8473e5333bf2bdfcbbd7d8709b94720ab44419c5`

## Question

What reusable development knowledge should DevOS retain from the agi-memory and adebench review without importing either project or duplicating capabilities they already implement?

## Repository-state findings

### F1 — Retrieval success and safe use are separate evaluation axes

`agi-memory` already distinguishes retrieval from actionability. Its current backlog records an evaluation where retrieval can remain successful while actionability degrades when rationale, supersession pointers, or abandoned-session warnings are removed.

**Disposition:** `CONFIRMS` existing DevOS evaluation law. Keep transfer/regression evaluation multi-dimensional rather than collapsing capability to one score.

### F2 — Runtime-derived metadata is more reliable than agent-volunteered metadata

The agi-memory maintainer measured a 14,748-record vault and found that optional rationale and supersession metadata were almost never populated by real work, while origin values established directly by code paths were populated reliably.

**Candidate lesson:** when a property materially affects safety, retrieval, authority interpretation, or lifecycle, prefer deriving/enforcing it structurally in the runtime over asking an agent to volunteer it.

**Disposition:** `NEW_CANDIDATE`. This should become a reusable procedural/negative lesson only after held-out transfer in DevOS work.

### F3 — Benchmark claims need probe hygiene and honest denominators

`agi-memory` widened an identifier benchmark after external review exposed that a 1/1 probe had been presented beside much larger categories. Its degraded-query evaluation now rejects leaking probes and fixes a precision budget before recall changes.

**Disposition:** `CONFIRMS` DevOS benchmark-claim identity and anti-self-grading discipline. Extend future benchmark receipts with explicit probe-count/denominator and fixture-leakage checks when applicable.

### F4 — The strongest remaining gap is after retrieval

`agi-memory` currently evaluates storage, retrieval, actionability of returned blocks, lifecycle state, supersession, origin, and degraded-query behavior. `adebench` evaluates a later boundary: the text a client actually receives after composition, ordering, cutoff, and competing payload pressure.

This yields a narrower candidate than "improve retrieval":

> A required fact may be stored correctly, retrieved correctly, and rendered actionably, yet still disappear or become ambiguous in the final bounded context delivered to the model.

**Disposition:** `NEW_CANDIDATE` named **delivered-context fitness**.

## Cross-reference against DevOS 0.13.0

DevOS already provides:

- branch-aware bounded context packets;
- provenance and staleness reporting;
- evidence lineage and triangulation;
- reflection candidates with disconfirmation tests;
- transfer/regression/canary evaluation tiers;
- exact-revision promotion gates.

No evidence from this review justifies importing agi-memory, adding a fifth memory subsystem, or replacing DevOS retrieval. The useful delta is evaluative, not architectural.

## Candidate capability

`devos.context.delivery_fitness`

**Purpose:** determine whether required evidence survives from selected DevOS packet to the context actually delivered at a consuming boundary.

Suggested fitness dimensions:

1. required-fact survival after composition/cutoff;
2. stale/current collision detection;
3. duplicate-context budget cost;
4. abstention when evidence is absent;
5. provenance/authority labels surviving delivery;
6. resilience under bounded competing payload pressure;
7. explicit denominator, margin, and coverage reporting.

## Candidate procedure

`DELIVERED_CONTEXT_FITNESS_01`

```text
freeze task + required answer fields
→ build normal DevOS packet
→ compose through a declared delivery adapter/budget
→ inject deterministic competing payload pressure
→ inspect final delivered text
→ score required-field survival separately from retrieval
→ record duplicate/stale/authority-loss failures
→ compare against baseline
```

The delivery adapter must be deterministic. No LLM judge is required for T0-T3 evaluation. A later T5 canary may test whether a real agent uses the delivered evidence correctly, but that is a separate metric.

## Disconfirmation test

Construct held-out tasks where the current DevOS packet contains every required answer field. If downstream composition under realistic declared budgets never drops, duplicates, obscures, or mixes stale required evidence across multiple consuming surfaces, then a dedicated delivery-fitness capability is unnecessary and this candidate should be closed as `NO_OP`.

## Negative knowledge

Do not propose the following to agi-memory as novel findings from this review:

- supersession pointers;
- rationale capture;
- origin labels;
- retrieval-vs-actionability separation;
- degraded-query/probe-hygiene evaluation.

Those are already implemented or explicitly documented in its current repository state.

## Provenance

Primary execution-truth references:

- `https://github.com/kdbhalala/agi-memory/tree/3c93e9e52b4038578501e2bbe4c374476d6db34f`
- `https://github.com/adecubed/adebench/tree/8473e5333bf2bdfcbbd7d8709b94720ab44419c5`
- `https://github.com/neohack2023/Dev-os/tree/4357d080043e0db56a919d3887dc2f10a833603d`

Reddit discussion is practitioner evidence and invitation context, not repository authority.

## Promotion boundary

This artifact records candidate knowledge only. It does not change DevOS authority, retrieval policy, or implementation. Any implementation should start as a bounded evaluator slice with deterministic fixtures and must pass held-out transfer and regression checks before STONE → MASON promotion is considered.
