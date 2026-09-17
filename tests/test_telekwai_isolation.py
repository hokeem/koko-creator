import unittest
from unittest.mock import patch

import app


class TelekwaiIsolationTests(unittest.TestCase):
    def test_synced_telekwai_is_visible_to_admin_but_not_recommended(self) -> None:
        telekwai_id = "a" * 32
        normal_id = "b" * 32
        scripts = [
            {
                "entry_id": telekwai_id,
                "title": "Telekwai script",
                "whole_video_summary": "Summary",
                "html_url": "https://example.com/telekwai.html",
                "telekwai": True,
                "script_type": "telekwai",
                "published": False,
            },
            {
                "entry_id": normal_id,
                "title": "Regular script",
                "whole_video_summary": "Summary",
                "html_url": "https://example.com/regular.html",
                "published": True,
            },
        ]
        with (
            patch.object(app, "maybe_sync_library"),
            patch.object(app, "entry_files_signature", return_value=object()),
            patch.object(app, "load_entries_raw_files", return_value=scripts),
            patch.object(app, "load_overrides", return_value={}),
        ):
            recommendations = app.recommendation_payload([], 10)
            admin_scripts = app.load_admin_entries("telekwai")

        self.assertEqual([item["entry_id"] for item in recommendations["entries"]], [normal_id])
        self.assertEqual([item["entry_id"] for item in admin_scripts], [telekwai_id])
        self.assertTrue(app.public_admin_entry(admin_scripts[0])["telekwai"])

    def test_admin_override_cannot_publish_telekwai(self) -> None:
        script = {"telekwai": True, "published": False}
        self.assertFalse(app.apply_entry_override(script, {"hidden": False})["creator_published"])


if __name__ == "__main__":
    unittest.main()
