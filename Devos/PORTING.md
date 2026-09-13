# Porting DevOS into an existing repository

## Install

1. Copy the complete `Devos/` directory into the host repository root.
2. Initialize the host:

```bash
python Devos/runtime/devos.py init \
  --scope my-project \
  --repository owner/repo \
  --project-name "My Project"
```

3. Replace or extend the starter `project-core` branch with real retrieval/ownership boundaries.
4. Add bounded work to `Devos/tasks.jsonl`; record lifecycle changes in `Devos/task-events.jsonl`.
5. Validate the queue and repository:

```bash
python Devos/runtime/task_queue.py validate
python Devos/runtime/devos.py validate
```

6. Build the local knowledge projection:

```bash
python Devos/runtime/build_knowledge_db.py build
python Devos/runtime/build_knowledge_db.py health
```

7. Generate branch-aware packets as needed:

```bash
python Devos/runtime/knowledge_runtime.py packet "search terms" --branch project-core
```

8. Admit evidence only from explicit evidence-episode JSON:

```bash
python Devos/runtime/evidence_store.py admit path/to/evidence-episode.json
```

9. Derive reflection candidates only from admitted evidence deltas:

```bash
python Devos/runtime/reflection_store.py \
  --db Devos/state/devos-knowledge.db \
  reflect --delta <delta-id> --request path/to/reflection-request.json
```

10. Admit learning only from bundles that resolve to stored reflections:

```bash
python Devos/runtime/learning_store.py \
  --db Devos/state/devos-knowledge.db \
  admit path/to/learning-bundle.json

python Devos/runtime/learning_store.py \
  --db Devos/state/devos-knowledge.db \
  list --branch project-core
```

11. Create and verify promotion envelopes only after transfer/regression gates pass:

```bash
python Devos/runtime/promotion_gate.py \
  --db Devos/state/devos-knowledge.db \
  propose path/to/promotion-request.json

python Devos/runtime/promotion_gate.py \
  --db Devos/state/devos-knowledge.db \
  verify --envelope <promotion-envelope-id> path/to/promotion-verification.json
```

12. Wire host CI to package validation plus applicable subsystem tests/build/packet/evidence/reflection/learning/promotion checks.

## Package-owned vs instance-owned

Package-owned files are contracts, schemas, templates, runtime code, tests, version metadata, checkpoints, and documentation.

Instance-owned files are generated for each host: `project.json`, `branches.jsonl`, `tasks.jsonl`, `task-events.jsonl`, `opportunities.jsonl`, `tools.jsonl`, `governance-lock.json`, and `research-policy.json`.

Receipts and runtime databases are host state. They must not be copied from one project into another as bootstrap defaults.

## Knowledge DB rebuild boundary

A normal knowledge DB build replaces only repository-derived projection tables and preserves durable runtime-owned state such as `runtime_kv`, evidence tables, reflection candidates, learning procedures, evaluations, experiences, capabilities, capability lifecycle events, promotion envelopes, and promotion decisions. Use `build --fresh` only when destructive reset is intended.

## Knowledge runtime boundary

Context packet generation is read-only against an existing projection. It reports source drift and does not silently rebuild stale state unless refresh is explicitly requested.

## Evidence boundary

Evidence is durable runtime state, not a projection and not authority. Do not foreign-key durable evidence to rebuildable projection tables such as `branch_state`; validate branch identity at admission instead.

Identical evidence replay is idempotent. Reusing a root or finding ID with different content is a hard conflict.

## Reflection boundary

Reflection is derived from admitted evidence deltas and remains authority-neutral.

A reflection request must:

- cite only evidence references present on its source delta,
- include at least one competing explanation,
- include a predicted consequence,
- include a required disconfirmation test,
- remain branch-scoped.

Do not treat self-generated reflection text or numeric confidence as evidence. A reflection candidate cannot mutate authority, update canon, or mark itself accepted. New evidence and governed evaluation are required before STONE -> MASON promotion can even be considered.

Reflection candidates are durable runtime state and survive normal projection rebuilds. Like evidence, they validate branch identity at admission rather than foreign-keying into rebuildable projection tables.

## Learning boundary

Learning is candidate consolidation, not authority promotion.

A learning bundle must reference one or more stored reflection candidates. The procedure's evidence references must be a subset of evidence already preserved by those reflections. This prevents the learning layer from laundering new claims into its own provenance.

Evaluation uses explicit tiers:

- T0 invariant/contract
- T1 known/training cases
- T2 development variations
- T3 held-out transfer
- T4 adversarial/regression
- T5 real-work canary

T3 input identities must be non-empty and disjoint from T1/T2. Passing T0-T3 is required for `TRANSFER`. T4 and T5 are recorded as regression/canary properties but do not imply higher maturity in this slice.

Candidate memory types are episodic, semantic, procedural, and negative. Exact replay is idempotent. Capability lifecycle history appends only when the learned state changes. Do not use SQLite `INSERT OR REPLACE` for current capability rows because replacement semantics can cascade-delete lifecycle history; use a true UPSERT.

All learning outputs retain `authority_effect: NONE` and `promotion_state: CANDIDATE_ONLY`. Learning may nominate reusable procedures or capabilities but may not mutate repository canon or bypass STONE -> MASON.

## Promotion boundary

Promotion is a verifier-gated handoff, not a repository mutation.

A promotion request must resolve to a stored capability whose latest evaluation passed T3 held-out transfer and T4 regression safety. The locked STONE envelope captures its procedure/reflection/evidence lineage, exact candidate Git SHA, change SHA-256, repository target, bounded paths, expected benefit, regression risk, falsification test, rollback plan, verifier policy, and required authorization.

Every verifier artifact is bound to the exact candidate revision. Required checks match both name and verifier source. When configured, independent review cannot be self-review and canary verification must come from the configured canary source.

The gate derives `PROMOTE`, `REVISE`, `ROLLBACK`, or `NO_OP`. `PROMOTE` and `ROLLBACK` only request MASON review. They do not authorize push, merge, deployment, canon mutation, or upstream sync. Host branch/ruleset/environment protections remain the execution authority.

Promotion envelopes and decisions survive normal projection rebuilds and remain `CANDIDATE_ONLY`, `authority_effect: NONE`, and `write_authorized: false`.

## Validation boundary

Normal validation checks that registered branch surfaces actually exist in the host repository. `repo_validator.py --skip-surface-checks validate` exists only for staged migrations.

## Upgrade rule

An upgrade may replace package-owned files. It must preserve instance-owned files unless an explicit migration declares and verifies a transformation.

When a subsystem schema changes, migrate host state explicitly. Never silently rewrite a project's queue, evidence, reflection, learning, promotion, authority state, or runtime-owned database state during package upgrade.
