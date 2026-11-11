import unittest

import app


class IntroRecommendationsTests(unittest.TestCase):
    def test_pinned_order_precedes_newer_scripts_and_ignores_bad_labels(self) -> None:
        ids = app.INTRO_SCRIPT_IDS
        entries = [
            {"entry_id": entry_id, "content_type": content_type, "created_at": "2026-01-01"}
            for entry_id, content_type in [
                (ids["friends"][0], "家庭整蛊"),
                (ids["friends"][1], "朋友整蛊"),
                (ids["friends"][2], "夫妻整蛊/冲突"),
                *[(entry_id, "夫妻整蛊/冲突") for entry_id in ids["couple"]],
            ]
        ]
        entries.append({"entry_id": "newer", "content_type": "朋友整蛊", "created_at": "2026-12-01"})
        self.assertEqual(
            [entry["entry_id"] for entry in app.recommendation_sequence(entries, ["friends"])[:3]],
            ids["friends"],
        )
        self.assertEqual(
            [entry["entry_id"] for entry in app.recommendation_sequence(entries, ["couple"])[:4]],
            ids["couple"],
        )

    def test_page_loads_intro_ui(self) -> None:
        self.assertIn("/static/intro-recommendations.js?v=1", app.page_html())


if __name__ == "__main__":
    unittest.main()
