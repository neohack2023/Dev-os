from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_HOST = ROOT / "tests" / "fixtures" / "repo_validator" / "host"
spec = importlib.util.spec_from_file_location("repo_validator", ROOT / "runtime" / "repo_validator.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class RepoValidatorTests(unittest.TestCase):
    def copy_fixture(self, td: str) -> Path:
        host = Path(td) / "host"
        shutil.copytree(FIXTURE_HOST, host)
        return host

    def test_valid_portable_fixture(self):
        self.assertEqual([], mod.validate_repository(FIXTURE_HOST / "Devos", FIXTURE_HOST))

    def test_governance_scope_must_match_project(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "governance-lock.json"
            data = json.loads(path.read_text())
            data["scope_key"] = "wrong"
            path.write_text(json.dumps(data))
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("governance scope_key" in e for e in errors), errors)

    def test_missing_surface_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "branches.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            rows[0]["surfaces"] = ["does-not-exist"]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("surface does not exist" in e for e in errors), errors)

    def test_branch_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "branches.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            rows[0]["dependencies"] = ["tooling"]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("branch dependency cycle" in e for e in errors), errors)

    def test_tool_revision_must_be_pinned(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "tools.jsonl"
            row = json.loads(path.read_text())
            row["verified_revision"] = "main"
            path.write_text(json.dumps(row) + "\n")
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("40-char commit SHA" in e for e in errors), errors)

    def test_live_external_memory_cannot_be_required_for_normal_work(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "governance-lock.json"
            data = json.loads(path.read_text())
            data["ordinary_repo_work_requires_live_external_memory"] = True
            path.write_text(json.dumps(data))
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("must not require live external memory" in e for e in errors), errors)

    def test_task_queue_routes_must_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            host = self.copy_fixture(td)
            path = host / "Devos" / "tasks.jsonl"
            row = json.loads(path.read_text())
            row["branch_keys"] = ["missing-branch"]
            path.write_text(json.dumps(row) + "\n")
            errors = mod.validate_repository(host / "Devos", host)
            self.assertTrue(any("task queue invalid" in e and "unknown branch" in e for e in errors), errors)

if __name__ == "__main__":
    unittest.main()
