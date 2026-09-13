#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json
from pathlib import Path
from typing import Any

PACKAGE_VERSION = "0.6.0"
INSTANCE_FILES = (
    "project.json", "branches.jsonl", "tasks.jsonl", "task-events.jsonl",
    "opportunities.jsonl", "tools.jsonl", "governance-lock.json", "research-policy.json",
)

def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json(path: Path, data: dict[str, Any], force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _load_runtime_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load runtime module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def init_instance(devos_root: Path, scope: str, repository: str, project_name: str, force: bool = False) -> None:
    devos_root = devos_root.resolve()
    template = _read_json(devos_root / "templates" / "project.json")
    template.update({"project_name": project_name, "scope_key": scope, "repository": repository, "devos_version": PACKAGE_VERSION})
    _write_json(devos_root / "project.json", template, force)
    branch_template = (devos_root / "templates" / "branches.jsonl").read_text(encoding="utf-8")
    branch_path = devos_root / "branches.jsonl"
    if branch_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {branch_path}")
    branch_path.write_text(branch_template.replace("__SCOPE__", scope), encoding="utf-8")
    for name in ("tasks.jsonl", "task-events.jsonl", "opportunities.jsonl", "tools.jsonl"):
        path = devos_root / name
        if path.exists() and not force:
            raise FileExistsError(f"refusing to overwrite {path}")
        path.write_text("", encoding="utf-8")
    research = _read_json(devos_root / "templates" / "research-policy.json")
    _write_json(devos_root / "research-policy.json", research, force)
    governance = {
        "schema_version": 1,
        "scope_key": scope,
        "repository": repository,
        "repo_execution_authority": "github",
        "external_memory_authority": "configured-by-host",
        "upstream_sync_required_for_authority_change": True,
        "ordinary_repo_work_requires_live_external_memory": False
    }
    _write_json(devos_root / "governance-lock.json", governance, force)

def validate(devos_root: Path, package_only: bool = False) -> list[str]:
    errors: list[str] = []
    required = [
        "README.md", "AGENTS.md", "VERSION", "manifest.json", "PORTING.md",
        "runtime/devos.py", "runtime/task_queue.py", "runtime/repo_validator.py",
        "runtime/db_runtime.py", "runtime/build_knowledge_db.py", "runtime/knowledge_runtime.py",
        "runtime/evidence_runtime.py", "runtime/evidence_store.py",
        "templates/project.json", "templates/branches.jsonl",
        "contracts/STONE.md", "contracts/MASON.md", "contracts/SELF_IMPROVEMENT.md",
        "contracts/TASK_QUEUE.md", "contracts/REPO_VALIDATION.md", "contracts/RUNTIME_DB.md",
        "contracts/KNOWLEDGE_RUNTIME.md", "contracts/EVIDENCE_RUNTIME.md",
        "schemas/task.schema.json", "schemas/task-event.schema.json", "schemas/runtime-db-v1.sql",
        "schemas/runtime-db-v2.sql", "schemas/context-packet.schema.json", "schemas/evidence-episode.schema.json",
        "tests/test_task_queue.py", "tests/test_repo_validator.py", "tests/test_knowledge_db.py",
        "tests/test_knowledge_runtime.py", "tests/test_evidence_runtime.py",
        "tests/fixtures/task_queue/tasks.jsonl", "tests/fixtures/task_queue/task-events.jsonl",
        "tests/fixtures/task_queue/branches.jsonl",
        "tests/fixtures/repo_validator/host/Devos/project.json",
        "tests/fixtures/repo_validator/host/Devos/governance-lock.json",
        "tests/fixtures/repo_validator/host/Devos/branches.jsonl",
        "tests/fixtures/repo_validator/host/Devos/tasks.jsonl",
        "tests/fixtures/repo_validator/host/Devos/task-events.jsonl",
        "tests/fixtures/repo_validator/host/Devos/tools.jsonl",
        "tests/fixtures/knowledge_db/host/README.md",
        "tests/fixtures/knowledge_db/host/docs/architecture.md",
        "tests/fixtures/knowledge_db/host/Devos/project.json",
        "tests/fixtures/knowledge_db/host/Devos/governance-lock.json",
        "tests/fixtures/knowledge_db/host/Devos/branches.jsonl",
        "tests/fixtures/knowledge_db/host/Devos/tasks.jsonl",
        "tests/fixtures/knowledge_db/host/Devos/task-events.jsonl",
        "tests/fixtures/knowledge_db/host/Devos/tools.jsonl",
        "tests/fixtures/evidence/episode-convergence.json",
        "checkpoints/KNOWLEDGE_DB_PORT_01.md", "checkpoints/KNOWLEDGE_RUNTIME_PORT_01.md",
        "checkpoints/EVIDENCE_RUNTIME_PORT_01.md", "state/.gitignore",
    ]
    for rel in required:
        if not (devos_root / rel).is_file():
            errors.append(f"missing package file: {rel}")
    if (devos_root / "VERSION").is_file():
        version = (devos_root / "VERSION").read_text(encoding="utf-8").strip()
        if version != PACKAGE_VERSION:
            errors.append(f"VERSION mismatch: {version!r} != {PACKAGE_VERSION!r}")
    if not package_only:
        for rel in INSTANCE_FILES:
            if not (devos_root / rel).is_file():
                errors.append(f"missing instance file: {rel}")
        project = devos_root / "project.json"
        if project.is_file():
            try:
                data = _read_json(project)
                for key in ("project_name", "scope_key", "repository", "devos_version"):
                    if not data.get(key):
                        errors.append(f"project.json missing {key}")
            except Exception as exc:
                errors.append(f"invalid project.json: {exc}")
        validator_path = devos_root / "runtime" / "repo_validator.py"
        if validator_path.is_file():
            try:
                validator = _load_runtime_module(validator_path, "devos_repo_validator")
                errors.extend(validator.validate_repository(devos_root, devos_root.parent))
            except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
                errors.append(f"repository validator failed to load: {exc}")
    return errors

def fingerprint(devos_root: Path) -> str:
    h = hashlib.sha256()
    excluded = set(INSTANCE_FILES) | {"receipts"}
    for path in sorted(p for p in devos_root.rglob("*") if p.is_file()):
        rel = path.relative_to(devos_root)
        if rel.parts[0] in excluded or str(rel) in excluded or rel.parts[0] == "state":
            continue
        h.update(str(rel).encode("utf-8")); h.update(b"\0"); h.update(path.read_bytes()); h.update(b"\0")
    return h.hexdigest()

def status(devos_root: Path) -> dict[str, Any]:
    initialized = (devos_root / "project.json").is_file()
    data: dict[str, Any] = {"devos_version": PACKAGE_VERSION, "initialized": initialized, "fingerprint": fingerprint(devos_root)}
    if initialized:
        project = _read_json(devos_root / "project.json")
        data.update({k: project.get(k) for k in ("project_name", "scope_key", "repository")})
    return data

def main() -> int:
    parser = argparse.ArgumentParser(description="Portable DevOS bootstrap and validation CLI")
    parser.add_argument("--devos-root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--scope", required=True)
    p_init.add_argument("--repository", required=True)
    p_init.add_argument("--project-name", required=True)
    p_init.add_argument("--force", action="store_true")
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--package-only", action="store_true")
    sub.add_parser("status")
    args = parser.parse_args()
    root = args.devos_root.resolve()
    try:
        if args.command == "init":
            init_instance(root, args.scope, args.repository, args.project_name, args.force)
            print(json.dumps(status(root), indent=2, sort_keys=True))
        elif args.command == "validate":
            errors = validate(root, args.package_only)
            if errors:
                print(json.dumps({"ok": False, "errors": errors}, indent=2)); return 1
            print(json.dumps({"ok": True, "devos_version": PACKAGE_VERSION}, indent=2))
        else:
            print(json.dumps(status(root), indent=2, sort_keys=True))
    except (FileExistsError, FileNotFoundError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2)); return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
