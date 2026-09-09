import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from security_inventory import INVENTORY, scan, source_files, validate


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(INVENTORY.read_text())
        cls.discovered = scan(source_files(ROOT), ROOT)

    def test_every_current_route_is_reviewed(self):
        self.assertEqual(validate(self.discovered, self.inventory), [])

    def test_missing_entry_fails(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["routes"].pop()
        self.assertTrue(any("UNINVENTORIED" in e for e in validate(self.discovered, inventory)))

    def test_new_method_fails(self):
        discovered = copy.deepcopy(self.discovered)
        discovered["routes"].append(dict(discovered["routes"][0], method="TRACE"))
        self.assertTrue(any("UNINVENTORIED" in e for e in validate(discovered, self.inventory)))

    def test_stale_route_fails(self):
        discovered = copy.deepcopy(self.discovered)
        discovered["routes"].pop()
        self.assertTrue(any("STALE" in e for e in validate(discovered, self.inventory)))

    def test_duplicate_route_fails(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["routes"].append(inventory["routes"][0])
        self.assertTrue(any("Duplicate" in e for e in validate(self.discovered, inventory)))

    def test_capability_typo_fails(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["routes"][0]["capabilities"] = ["anything"]
        self.assertTrue(any("capability" in e for e in validate(self.discovered, inventory)))

    def test_new_public_exception_fails(self):
        inventory = copy.deepcopy(self.inventory)
        inventory["routes"][0]["capabilities"] = ["public.ui"]
        self.assertTrue(any("Public exception" in e for e in validate(self.discovered, inventory)))

    def scan_snippet(self, text):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "new_surface.py"
            source.write_text(text)
            return scan([source], root)

    def test_new_app_alias_methods_and_framework_routes_are_discovered(self):
        found = self.scan_snippet('''from fastapi import FastAPI as API
service = API()
@service.get('/new')
@service.head('/new')
def endpoint(): pass
''')
        keys = {(r["method"], r["path"]) for r in found["routes"]}
        self.assertIn(("GET", "/new"), keys)
        self.assertIn(("HEAD", "/new"), keys)
        self.assertIn(("HEAD", "/openapi.json"), keys)
        self.assertEqual(len(keys), 10)
        self.assertTrue(any("UNINVENTORIED" in e for e in validate(found, self.inventory)))

    def test_prefix_and_middleware_changes_require_review(self):
        found = self.scan_snippet('''from fastapi import FastAPI
app = FastAPI()
app.include_router(other.router, prefix='/new')
app.add_middleware(AuthMiddleware)
''')
        self.assertTrue(any("TOPOLOGY" in e for e in validate(found, self.inventory)))

    def test_unsupported_registration_fails_closed(self):
        for expression in ("app.mount('/files', files)", "app.add_api_route('/new', handler)",
                           "app.get('/new')(handler)", "other.include_router(router)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.scan_snippet("from fastapi import FastAPI\napp = FastAPI()\n" + expression)

    def test_undecodable_candidate_fails(self):
        with self.assertRaises(SyntaxError):
            self.scan_snippet("from fastapi import FastAPI\napp = FastAPI(\n")

    def test_originals_are_separate_from_browse_and_health_is_operator_only(self):
        routes = { (r["method"], r["path"]): r for r in self.inventory["routes"]
                   if r["source"] == "backend/app/main.py" }
        self.assertEqual(routes["GET", "/assets/{asset_id}/media"]["capabilities"],
                         ["library.read", "media.original.read"])
        self.assertEqual(routes["GET", "/health"]["capabilities"], ["system.read"])


if __name__ == "__main__":
    unittest.main()
