"""Isolated child-process wrapper for scoped worker handler qualification."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "security" / "scoped_worker_handler_fixture.py"
REQUIRED = ("numpy", "imagehash", "exifread", "prometheus_client", "sqlalchemy", "alembic")

@unittest.skipUnless(all(importlib.util.find_spec(name) for name in REQUIRED),
                     "worker qualification dependencies unavailable in this environment")
class ScopedWorkerHandlerProcessTests(unittest.TestCase):
    def test_actual_handlers_run_in_fresh_child(self):
        with tempfile.TemporaryDirectory(prefix="scoped-worker-child-") as cwd:
            result = subprocess.run([sys.executable, "-I", str(FIXTURE)], cwd=cwd,
                                    capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Ran 7 tests", result.stderr + result.stdout)
        self.assertIn("OK", result.stderr + result.stdout)

if __name__ == "__main__":
    unittest.main()
