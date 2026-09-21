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
            shared_entry = app.entry_by_id(telekwai_id)
            admin_scripts = app.load_admin_entries("telekwai")

        self.assertEqual([item["entry_id"] for item in recommendations["entries"]], [normal_id])
        self.assertIsNotNone(shared_entry)
        self.assertEqual(shared_entry["entry_id"], telekwai_id)
        self.assertTrue(shared_entry["creator_published"])
        self.assertFalse(shared_entry["creator_recommended"])
        self.assertEqual([item["entry_id"] for item in admin_scripts], [telekwai_id])
        self.assertTrue(app.public_admin_entry(admin_scripts[0])["telekwai"])

        total, profile_recommendations = app.ranked_scripts_for_creator(
            ["夫妻"],
            entries=[shared_entry, app.apply_entry_override(scripts[1], None)],
        )
        self.assertEqual(total, 1)
        self.assertEqual([item["entry_id"] for item in profile_recommendations], [normal_id])

    def test_legacy_unpublished_telekwai_stays_shareable_until_manually_hidden(self) -> None:
        script = {"telekwai": True, "published": False}
        visible = app.apply_entry_override(script, {"hidden": False})
        hidden = app.apply_entry_override(script, {"hidden": True})
        self.assertTrue(visible["creator_published"])
        self.assertFalse(visible["creator_recommended"])
        self.assertFalse(hidden["creator_published"])


if __name__ == "__main__":
    unittest.main()
