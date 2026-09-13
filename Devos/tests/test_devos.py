import json, tempfile, unittest
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("devos_cli", ROOT / "runtime" / "devos.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class DevOSTest(unittest.TestCase):
    def test_package_validates(self):
        self.assertEqual([], mod.validate(ROOT, package_only=True))

    def test_init_is_deterministic_and_guarded(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td) / "Devos"
            import shutil; shutil.copytree(ROOT, temp)
            mod.init_instance(temp, "demo", "owner/demo", "Demo")
            self.assertEqual([], mod.validate(temp))
            data = json.loads((temp / "project.json").read_text())
            self.assertEqual("demo", data["scope_key"])
            with self.assertRaises(FileExistsError):
                mod.init_instance(temp, "demo", "owner/demo", "Demo")

if __name__ == "__main__": unittest.main()
