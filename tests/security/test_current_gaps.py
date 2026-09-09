"""Characterization tests, not positive security acceptance. See denial CLI.

These assert today's insecure behavior so accidental harness failures (e.g. 422
or 500) cannot masquerade as demonstrated leaks. Remove/replace each assertion
with full-stack denial tests when that path gains real authorization.
"""
import unittest
from harness import Harness, run_probes


class CurrentGapTests(unittest.TestCase):
    def test_denial_matrix_reports_every_current_failure_without_skips(self):
        findings = run_probes()
        self.assertEqual(len(findings), 84)
        for finding in findings:
            with self.subTest(case=finding["case"]):
                self.assertFalse(finding["secure"])
                expected = ("accepted" if finding["case"].startswith("voice/") else
                            206 if finding["case"].endswith("video-range") else 200)
                self.assertEqual(finding["status"], expected)
                if "destructive-asset" in finding["case"]:
                    self.assertIn("files.delete", finding["effects"])
                    self.assertIn("db.commit", finding["effects"])
                if "operator-ingest" in finding["case"]:
                    self.assertIn("ingest.invoke", finding["effects"])
                if "foreign-conversation" in finding["case"]:
                    self.assertIn("provider.post", finding["effects"])

    def test_anonymous_range_returns_actual_synthetic_bytes(self):
        with Harness() as h:
            response = h.client.get("/assets/202/media", headers={"Range": "bytes=0-8"})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b"synthetic")
            self.assertEqual(response.headers["content-range"], "bytes 0-8/32")

    def test_download_and_cached_derivatives_disclose_bytes(self):
        with Harness() as h:
            response = h.client.get("/assets/202/media?download=true")
            self.assertIn("attachment", response.headers["content-disposition"])
            self.assertTrue(response.content.startswith(b"synthetic-video"))
            for path in ("/assets/202/thumbnail", "/faces/202/crop"):
                self.assertEqual(h.client.get(path).content, b"synthetic-derived-bytes")

    def test_deleted_asset_still_reaches_original_handler(self):
        with Harness() as h:
            h.db.rows[h.ns["Asset"]][1].status = "deleted"
            self.assertEqual(h.client.get("/assets/202/media").status_code, 200)

    def test_foreign_album_cover_caption_and_global_count_are_returned(self):
        with Harness() as h:
            album = h.client.get("/albums/drafts/404").json()["album"]
            self.assertEqual(album["cover_asset_id"], 202)
            self.assertEqual(album["items"][0]["id"], 202)
            captions = h.client.get("/assets/202/captions").json()
            self.assertEqual(captions["asset_id"], 202)
            self.assertEqual(captions["captions"][0]["text"], "Synthetic family-b caption")
            self.assertEqual(h.client.get("/assets").json()["total"], 2)
            self.assertEqual(h.client.get("/search").json()["total"], 2)

    def test_absent_objects_are_not_misreported_as_auth_denial(self):
        with Harness() as h:
            self.assertEqual(h.client.get("/assets/999/media").status_code, 404)
            self.assertEqual(h.client.get("/assets/202/media").status_code, 200)

    def test_voice_feature_gate_is_preserved_but_enabled_is_not_identity(self):
        with Harness() as h:
            enabled_settings = h.ns["get_settings"]()
            enabled_settings.voice_enabled = False
            h.ns["get_settings"] = lambda: enabled_settings
            response = h.client.post("/voice/chat/delete", json={"conversation_id": "synthetic"})
            self.assertEqual(response.status_code, 501)
            self.assertNotIn("provider.post", h.db.effects)

    def test_confirmation_rejects_wrong_token_but_accepts_omission(self):
        with Harness() as h:
            h.ns["_put_pending_action"]("synthetic-client", "rename", {"person_id": 202})
            self.assertIsNone(h.ns["_pop_pending_action"]("synthetic-client", "wrong-token"))
            self.assertIsNotNone(h.ns["_pop_pending_action"]("synthetic-client", None))
            self.assertIsNone(h.ns["_pop_pending_action"]("synthetic-client", None))

    def test_framework_head_exists_but_legacy_get_does_not_add_head(self):
        with Harness() as h:
            self.assertEqual(h.client.head("/openapi.json").status_code, 200)
            self.assertEqual(h.client.head("/assets/202/media").status_code, 405)
            self.assertEqual(h.client.options("/assets/202/media").status_code, 405)


if __name__ == "__main__":
    unittest.main()
