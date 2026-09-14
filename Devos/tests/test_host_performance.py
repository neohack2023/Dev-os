import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("host_performance", ROOT / "runtime" / "host_performance.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class HostPerformanceTest(unittest.TestCase):
    def test_snapshot_contract(self):
        data = mod.collect_snapshot(sample_ms=50)
        self.assertEqual("devos.host_performance.v1", data["schema_version"])
        self.assertEqual("NONE", data["provenance"]["authority_effect"])
        self.assertIn(data["pressure"]["level"], {"NORMAL", "ELEVATED", "HIGH", "CRITICAL"})
        self.assertGreaterEqual(data["cpu"]["logical_processors"], 1)
        self.assertTrue(data["disks"])

    def test_atomic_output_round_trip(self):
        payload = mod.collect_snapshot(sample_ms=50)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "latest.json"
            text = mod.write_json(payload, out)
            self.assertEqual(payload, json.loads(out.read_text(encoding="utf-8")))
            self.assertEqual(payload, json.loads(text))

    def test_pressure_thresholds(self):
        self.assertEqual("NORMAL", mod.classify_pressure(10, 20, [{"used_percent": 30}])["level"])
        self.assertEqual("ELEVATED", mod.classify_pressure(70, 20, [{"used_percent": 30}])["level"])
        self.assertEqual("HIGH", mod.classify_pressure(10, 85, [{"used_percent": 30}])["level"])
        self.assertEqual("CRITICAL", mod.classify_pressure(10, 20, [{"used_percent": 95}])["level"])

if __name__ == "__main__": unittest.main()
