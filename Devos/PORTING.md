# Porting DevOS into an existing repository

## Install

1. Copy the complete `Devos/` directory into the host repository root.
2. Run:

```bash
python Devos/runtime/devos.py init \
  --scope my-project \
  --repository owner/repo \
  --project-name "My Project"
```

3. Edit `Devos/branches.jsonl` to describe real retrieval/ownership boundaries.
4. Wire host tests/CI to `python Devos/runtime/devos.py validate`.
5. Add host-specific tools, authority adapters, and memory connectors through governed changes rather than editing distribution defaults ad hoc.

## Package-owned vs instance-owned

Package-owned files are contracts, schemas, templates, runtime code, tests, version metadata, and documentation.

Instance-owned files are generated for each host: `project.json`, `branches.jsonl`, `tasks.jsonl`, `task-events.jsonl`, `opportunities.jsonl`, `tools.jsonl`, `governance-lock.json`, and `research-policy.json`.

Receipts and runtime databases are host state. They must not be copied from one project into another as bootstrap defaults.

## Upgrade rule

An upgrade may replace package-owned files. It must preserve instance-owned files unless an explicit migration declares and verifies a transformation.
