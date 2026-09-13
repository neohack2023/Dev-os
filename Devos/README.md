# DevOS Portable Package

DevOS is repository-side development intelligence: routing, evidence boundaries, bounded research, reflection, task state, tool knowledge, governed learning, a local queryable knowledge projection, branch-aware context packets, immutable local evidence, evidence-bounded reflection candidates, transfer-tested candidate capabilities, and an exact-revision promotion gate that live with the code they serve.

Everything owned by the package lives under `Devos/` so the folder can be copied into another repository intact.

Initialize a host repository with:

```bash
python Devos/runtime/devos.py init --scope my-project --repository owner/repo --project-name "My Project"
python Devos/runtime/devos.py validate
```

The distribution ships no host task history, receipts, sync history, runtime database, or project canon. Those are generated per repository.

## Portable executable subsystems

### Task queue

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/task_queue.py next
python Devos/runtime/task_queue.py next --canary
python Devos/runtime/task_queue.py show <task-id>
```

Declarations live in `Devos/tasks.jsonl`; append-only lifecycle overlays live in `Devos/task-events.jsonl`. Selection is deterministic and host-neutral.

### Repository validator

```bash
python Devos/runtime/repo_validator.py validate
```

The validator checks project/governance agreement, branch topology and host surfaces, task routing, tool pinning, path safety, and local-first authority rules without requiring live external memory.

### Knowledge database

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py query "search terms"
python Devos/runtime/build_knowledge_db.py health
```

The default database is `Devos/state/devos-knowledge.db`. Normal rebuilds refresh repository-derived projection tables while preserving durable runtime state. `build --fresh` is the explicit destructive reset.

### Knowledge runtime

```bash
python Devos/runtime/knowledge_runtime.py status
python Devos/runtime/knowledge_runtime.py packet "search terms" --branch project-core
```

The runtime turns the SQLite projection into bounded branch-aware context packets with deterministic ranking, provenance, staleness reporting, and packet hashes.

### Evidence runtime

```bash
python Devos/runtime/evidence_store.py admit path/to/evidence-episode.json
python Devos/runtime/evidence_store.py list
python Devos/runtime/evidence_store.py list --branch project-core
```

Evidence roots and atomic findings are admitted as durable SQLite state. Lineage collapse prevents derivatives and same-input reproductions from inflating independent support. Explicit cross-reference and triangulation produce review-oriented delta packets whose `authority_effect` is always `NONE`.

Evidence IDs are immutable: identical replay is idempotent, while reusing an ID with changed content is rejected. Normal knowledge projection rebuilds preserve evidence.

### Reflection core

```bash
python Devos/runtime/reflection_store.py --db Devos/state/devos-knowledge.db \
  reflect --delta <delta-id> --request path/to/reflection-request.json

python Devos/runtime/reflection_store.py --db Devos/state/devos-knowledge.db \
  list --branch project-core
```

Reflection starts from an admitted evidence delta. The request must cite evidence already present on that delta, provide a competing explanation, predict a consequence, and define a disconfirmation test.

Reflection candidates are deterministic, immutable/idempotent durable runtime state. They remain `CANDIDATE_ONLY` with `authority_effect: NONE`. Competing hypotheses over the same delta remain distinct candidates. Reflective prose cannot promote itself or manufacture evidence.

See `contracts/REFLECTION_CORE.md`, `schemas/reflection-request.schema.json`, and checkpoint `checkpoints/REFLECTION_CORE_PORT_01.md`.

### Learning layer

```bash
python Devos/runtime/learning_store.py --db Devos/state/devos-knowledge.db \
  admit path/to/learning-bundle.json

python Devos/runtime/learning_store.py --db Devos/state/devos-knowledge.db \
  list --branch project-core
```

Learning starts from stored reflection candidates, never from ungrounded prose. Procedure evidence must already be present in the source reflections, preserving the chain `evidence -> delta -> reflection -> learning`.

The portable evaluator records tiers T0 through T5. T3 is a held-out transfer gate whose input identities must be disjoint from T1/T2. Passing T0-T3 can raise a capability to `TRANSFER`. T4 and T5 are recorded separately as `regression_safe` and `canary_validated`; this slice does not infer `COMPOSITION`, `ADAPTATION`, or `METACOGNITIVE_CONTROL` from them.

Candidate memory forms are `EPISODIC`, `SEMANTIC`, `PROCEDURAL`, and `NEGATIVE`. Procedures, experiences, evaluations, and capability lifecycle events are durable runtime state and survive normal projection rebuilds. Exact replay is idempotent and does not invent another lifecycle event.

Every learning artifact remains `CANDIDATE_ONLY` with `authority_effect: NONE`. Learning can nominate reusable knowledge, but only the governed STONE -> MASON path may turn a candidate into repository authority.

See `contracts/LEARNING_LAYER.md` and checkpoint `checkpoints/LEARNING_LAYER_PORT_01.md`.

### Promotion gate

```bash
python Devos/runtime/promotion_gate.py --db Devos/state/devos-knowledge.db \
  propose path/to/promotion-request.json

python Devos/runtime/promotion_gate.py --db Devos/state/devos-knowledge.db \
  verify --envelope <promotion-envelope-id> path/to/promotion-verification.json

python Devos/runtime/promotion_gate.py --db Devos/state/devos-knowledge.db \
  list --branch project-core
```

Promotion starts only from stored learning capabilities whose latest evaluation passed held-out transfer and regression safety. STONE locks an envelope containing exact learning/reflection/evidence lineage, repository target, candidate Git SHA, change SHA-256, bounded paths, falsification test, rollback plan, verifier policy, and required authorization.

Verification is bound to the exact candidate revision. Required checks match by name and verifier source; configured review/canary evidence must also bind to that same revision. The runtime derives `PROMOTE`, `REVISE`, `ROLLBACK`, or `NO_OP`.

A `PROMOTE` result means only "eligible for MASON review/handoff." It never grants write authority. Every envelope and decision remains `CANDIDATE_ONLY`, `authority_effect: NONE`, and `write_authorized: false`.

See `contracts/PROMOTION_GATE.md` and checkpoint `checkpoints/PROMOTION_GATE_PORT_01.md`.

## Core law

- GitHub owns live repository execution truth.
- External memory is optional and configured by the host.
- STONE controls evidence intake and provenance.
- MASON controls durable assembly and verified writes.
- Research is bounded and need-triggered.
- Reflection may nominate improvements but cannot self-promote them.
- Learning requires transfer evidence and cannot self-promote.
- Promotion decisions bind to exact candidate revisions and still do not authorize writes.
- Repetition/prevalence never upgrades authority by itself.
- Ordinary repo work must remain possible from the checked-in local bundle.

See `PORTING.md` for installation and upgrade boundaries.
