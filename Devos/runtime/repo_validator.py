#!/usr/bin/env python3
"""Portable DevOS repository integrity validator.

Validates one initialized Devos/ instance against host-neutral repository,
governance, branch, task, and tool invariants. The validator deliberately
does not require live external memory and does not encode any host project ID.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

DEVOS_ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = DEVOS_ROOT.parent

ALLOWED_BRANCH_STATUS = {"active", "incubating", "candidate", "paused", "archived", "superseded"}
ALLOWED_TOOL_MATURITY = {"candidate", "verified", "deprecated"}
ALLOWED_CAPABILITY_QUALIFICATION = {"candidate", "verified", "unsupported"}
REQUIRED_PROJECT_FIELDS = {
    "schema_version", "project_name", "scope_key", "repository",
    "devos_version", "authority", "paths",
}
REQUIRED_BRANCH_FIELDS = {"branch_key", "scope_key", "title", "status", "dependencies", "surfaces"}
REQUIRED_TOOL_FIELDS = {
    "tool_key", "repository", "verified_revision", "usage_contract", "maturity",
    "capabilities", "known_limits", "entrypoints", "evidence", "last_verified",
}
REQUIRED_CAPABILITY_FIELDS = {"name", "scope", "languages", "qualification"}


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise ValueError(f"missing {label}: {path.name}")
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on {label} line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{label} line {line_no} must be a JSON object")
        rows.append(row)
    return rows


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _under(root: Path, relative: str) -> Path:
    if not _safe_relative_path(relative):
        raise ValueError(f"unsafe relative path: {relative}")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError(f"path escapes host root: {relative}")
    return candidate


def validate_project(
    devos_root: Path,
    errors: list[str],
    host_root: Path | None = None,
) -> dict[str, Any] | None:
    path = devos_root / "project.json"
    if not path.is_file():
        errors.append("missing project.json")
        return None
    try:
        project = _load_json(path, label="project.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid project.json: {exc}")
        return None

    missing = sorted(REQUIRED_PROJECT_FIELDS - set(project))
    if missing:
        errors.append(f"project.json missing: {', '.join(missing)}")
        return project

    if not isinstance(project.get("schema_version"), int) or project["schema_version"] < 1:
        errors.append("project.json schema_version must be a positive integer")
    for field in ("project_name", "scope_key", "repository", "devos_version"):
        if not _nonempty(project.get(field)):
            errors.append(f"project.json {field} must be a non-empty string")
    if _nonempty(project.get("scope_key")) and not re.fullmatch(r"[A-Za-z0-9._-]+", project["scope_key"]):
        errors.append("project.json scope_key must be a portable slug")
    if _nonempty(project.get("repository")) and not re.fullmatch(r"[^/\s]+/[^/\s]+", project["repository"]):
        errors.append("project.json repository must be owner/name")

    authority = project.get("authority")
    if not isinstance(authority, dict):
        errors.append("project.json authority must be an object")
    else:
        if authority.get("repository_execution") != "github":
            errors.append("project authority.repository_execution must be github")
        if not _nonempty(authority.get("external_memory")):
            errors.append("project authority.external_memory must be configured explicitly")

    paths = project.get("paths")
    if not isinstance(paths, dict):
        errors.append("project.json paths must be an object")
    else:
        required_paths = {"devos": "Devos", "runtime_state": "Devos/state", "receipts": "Devos/receipts"}
        project_host_root = (host_root or devos_root.parent).resolve()
        for key, expected in required_paths.items():
            value = paths.get(key)
            if value != expected:
                errors.append(f"project paths.{key} must be {expected}")
            elif not _safe_relative_path(value):
                errors.append(f"project paths.{key} is unsafe")
            else:
                try:
                    if not _under(project_host_root, value).exists():
                        errors.append(f"project paths.{key} does not exist: {value}")
                except ValueError as exc:
                    errors.append(f"project paths.{key}: {exc}")

    version_path = devos_root / "VERSION"
    if version_path.is_file() and _nonempty(project.get("devos_version")):
        installed = version_path.read_text(encoding="utf-8").strip()
        if project["devos_version"] != installed:
            errors.append(
                f"project.json devos_version {project['devos_version']} does not match installed VERSION {installed}"
            )
    return project


def validate_governance(devos_root: Path, project: dict[str, Any] | None, errors: list[str]) -> None:
    path = devos_root / "governance-lock.json"
    if not path.is_file():
        errors.append("missing governance-lock.json")
        return
    try:
        lock = _load_json(path, label="governance-lock.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid governance-lock.json: {exc}")
        return

    required = {
        "schema_version", "scope_key", "repository", "repo_execution_authority",
        "external_memory_authority", "upstream_sync_required_for_authority_change",
        "ordinary_repo_work_requires_live_external_memory",
    }
    missing = sorted(required - set(lock))
    if missing:
        errors.append(f"governance-lock.json missing: {', '.join(missing)}")
    if lock.get("repo_execution_authority") != "github":
        errors.append("governance lock repo_execution_authority must be github")
    if lock.get("ordinary_repo_work_requires_live_external_memory") is not False:
        errors.append("ordinary repo work must not require live external memory")
    if not isinstance(lock.get("upstream_sync_required_for_authority_change"), bool):
        errors.append("upstream_sync_required_for_authority_change must be boolean")
    if not _nonempty(lock.get("external_memory_authority")):
        errors.append("external_memory_authority must be explicit")

    if project:
        if lock.get("scope_key") != project.get("scope_key"):
            errors.append("governance scope_key does not match project.json")
        if lock.get("repository") != project.get("repository"):
            errors.append("governance repository does not match project.json")


def validate_branches(
    devos_root: Path,
    host_root: Path,
    project: dict[str, Any] | None,
    errors: list[str],
    *,
    check_surfaces: bool = True,
) -> list[dict[str, Any]]:
    try:
        rows = _load_jsonl(devos_root / "branches.jsonl", label="branches.jsonl")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return []
    if not rows:
        errors.append("branches.jsonl contains no branches")
        return rows

    keys: list[str] = []
    for line_no, row in enumerate(rows, 1):
        missing = sorted(REQUIRED_BRANCH_FIELDS - set(row))
        if missing:
            errors.append(f"branches.jsonl line {line_no} missing: {', '.join(missing)}")
            continue
        key = row.get("branch_key")
        if not _nonempty(key):
            errors.append(f"branches.jsonl line {line_no} has invalid branch_key")
            continue
        keys.append(key)
        if project and row.get("scope_key") != project.get("scope_key"):
            errors.append(f"{key}: scope_key does not match project scope")
        if not _nonempty(row.get("title")):
            errors.append(f"{key}: title required")
        if row.get("status") not in ALLOWED_BRANCH_STATUS:
            errors.append(f"{key}: invalid status {row.get('status')}")
        if not _string_list(row.get("dependencies"), allow_empty=True):
            errors.append(f"{key}: dependencies must be a list of non-empty strings")
        if not _string_list(row.get("surfaces"), allow_empty=False):
            errors.append(f"{key}: surfaces must be a non-empty list of paths")
            continue
        for surface in row["surfaces"]:
            if not _safe_relative_path(surface):
                errors.append(f"{key}: unsafe surface path {surface}")
                continue
            if check_surfaces:
                try:
                    if not _under(host_root, surface).exists():
                        errors.append(f"{key}: surface does not exist: {surface}")
                except ValueError as exc:
                    errors.append(f"{key}: {exc}")

    if len(keys) != len(set(keys)):
        errors.append("branch keys must be unique")
    known = set(keys)
    index = {row.get("branch_key"): row for row in rows if _nonempty(row.get("branch_key"))}
    for key, row in index.items():
        deps = row.get("dependencies")
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if dep not in known:
                errors.append(f"{key}: unknown dependency {dep}")
            if dep == key:
                errors.append(f"{key}: branch cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            errors.append(f"branch dependency cycle at {key}")
            return
        visiting.add(key)
        row = index.get(key, {})
        for dep in row.get("dependencies", []):
            if dep in index:
                visit(dep)
        visiting.remove(key)
        visited.add(key)

    for key in list(index):
        visit(key)
    return rows


def validate_tools(devos_root: Path, errors: list[str]) -> list[dict[str, Any]]:
    try:
        rows = _load_jsonl(devos_root / "tools.jsonl", label="tools.jsonl")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return []

    keys: list[str] = []
    for line_no, row in enumerate(rows, 1):
        missing = sorted(REQUIRED_TOOL_FIELDS - set(row))
        if missing:
            errors.append(f"tools.jsonl line {line_no} missing: {', '.join(missing)}")
            continue
        key = row.get("tool_key")
        if not _nonempty(key):
            errors.append(f"tools.jsonl line {line_no} has invalid tool_key")
            continue
        keys.append(key)
        if key != key.lower() or " " in key:
            errors.append(f"{key}: tool_key must be lowercase and space-free")
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", str(row.get("repository", ""))):
            errors.append(f"{key}: repository must be owner/name")
        revision = row.get("verified_revision")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            errors.append(f"{key}: verified_revision must be a full 40-char commit SHA")
        if row.get("maturity") not in ALLOWED_TOOL_MATURITY:
            errors.append(f"{key}: invalid maturity {row.get('maturity')}")
        if not _nonempty(row.get("usage_contract")):
            errors.append(f"{key}: usage_contract required")
        for field in ("known_limits", "entrypoints", "evidence"):
            if not _string_list(row.get(field), allow_empty=False):
                errors.append(f"{key}: {field} must be a non-empty string list")
        if not isinstance(row.get("last_verified"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["last_verified"]):
            errors.append(f"{key}: last_verified must be YYYY-MM-DD")
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            errors.append(f"{key}: at least one capability required")
            continue
        names: list[str] = []
        for idx, capability in enumerate(capabilities, 1):
            if not isinstance(capability, dict):
                errors.append(f"{key}: capability {idx} must be an object")
                continue
            missing_cap = sorted(REQUIRED_CAPABILITY_FIELDS - set(capability))
            if missing_cap:
                errors.append(f"{key}: capability {idx} missing: {', '.join(missing_cap)}")
                continue
            name = capability.get("name")
            if not _nonempty(name) or not _nonempty(capability.get("scope")):
                errors.append(f"{key}: capability {idx} name/scope required")
            else:
                names.append(name)
            if not _string_list(capability.get("languages"), allow_empty=False):
                errors.append(f"{key}: capability {idx} languages required")
            if capability.get("qualification") not in ALLOWED_CAPABILITY_QUALIFICATION:
                errors.append(f"{key}: capability {idx} invalid qualification")
        if len(names) != len(set(names)):
            errors.append(f"{key}: capability names must be unique")
    if len(keys) != len(set(keys)):
        errors.append("tool keys must be unique")
    return rows


def validate_queue(devos_root: Path, errors: list[str]) -> None:
    runtime_path = Path(__file__).resolve().parent / "task_queue.py"
    try:
        spec = importlib.util.spec_from_file_location("devos_task_queue_for_validator", runtime_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load task_queue runtime")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_instance_queue(devos_root)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        errors.append(f"task queue invalid: {exc}")


def validate_auxiliary_json(devos_root: Path, errors: list[str]) -> None:
    for name in ("research-policy.json",):
        path = devos_root / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        try:
            _load_json(path, label=name)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid {name}: {exc}")


def validate_repository(
    devos_root: Path,
    host_root: Path | None = None,
    *,
    check_surfaces: bool = True,
) -> list[str]:
    devos_root = devos_root.resolve()
    host_root = (host_root or devos_root.parent).resolve()
    errors: list[str] = []
    project = validate_project(devos_root, errors, host_root)
    validate_governance(devos_root, project, errors)
    validate_branches(devos_root, host_root, project, errors, check_surfaces=check_surfaces)
    validate_tools(devos_root, errors)
    validate_queue(devos_root, errors)
    validate_auxiliary_json(devos_root, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devos-root", type=Path, default=DEVOS_ROOT)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--skip-surface-checks", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    args = parser.parse_args()
    try:
        errors = validate_repository(
            args.devos_root,
            args.host_root,
            check_surfaces=not args.skip_surface_checks,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"ok": True}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
