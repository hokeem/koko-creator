import unittest
from unittest.mock import patch

import app


class CreatorWorkspaceSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = app.page_html()

    def test_recommendation_places_compact_preference_link_after_choice(self) -> None:
        feature = self.markup.index('data-reselect-link')
        choices = self.markup.index('data-feature-skip')
        self.assertGreater(feature, choices)
        self.assertIn('没有合适的视频？', self.markup)
        self.assertIn('重新选择内容偏好', self.markup)
        self.assertIn('Sem vídeo ideal?', self.markup)
        self.assertIn('Mudar preferências', self.markup)
        self.assertNotIn('Suas preferências', self.markup[self.markup.index('function featuredCard'):self.markup.index('function stopFeaturedVideo')])

    def test_profile_defaults_to_saved_and_shows_selection_time(self) -> None:
        self.assertIn('let savedTab="saved"', self.markup)
        self.assertIn('selectionTimeLabel(id)', self.markup)
        self.assertIn('class="selection-time"', self.markup)
        self.assertIn('selected-script-list', self.markup)

    def test_plan_choice_saves_and_records_timestamp_then_syncs_immediately(self) -> None:
        self.assertIn('workspace.saved.push(id)', self.markup)
        self.assertIn('workspace.selection_times[id]=new Date().toISOString()', self.markup)
        self.assertIn('persistAccountState(true)', self.markup)

    def test_dashboard_filters_invalid_recommendations_and_exposes_retry(self) -> None:
        self.assertIn('function normalizeRecommendationEntries(value)', self.markup)
        self.assertIn('entries=normalizeRecommendationEntries(cached.entries)', self.markup)
        self.assertIn('let loaded=normalizeRecommendationEntries(d.entries)', self.markup)
        self.assertIn('data-retry-dashboard', self.markup)
        self.assertIn('Creator dashboard render failed', self.markup)
        self.assertIn('Creator reward progress failed', self.markup)
        self.assertIn('Creator featured card failed', self.markup)
        self.assertIn('s&&typeof s==="object"', self.markup)

    def test_account_state_keeps_timestamp_only_for_saved_scripts(self) -> None:
        account = {"account_id": "creator-test", "state": {}}
        workspace = {
            "saved": ["script-a", "script-a", "script-b"],
            "selection_times": {
                "script-a": "2026-10-12T07:00:00.000Z",
                "script-b": "2026-10-12T07:01:00.000Z",
                "script-c": "2026-10-12T07:02:00.000Z",
            },
        }
        with patch.object(app, "load_accounts", return_value=[account]), patch.object(app, "save_accounts") as save_accounts, patch.object(app, "public_account", side_effect=lambda item, include_state=False: item):
            result = app.update_account_state("creator-test", {"workspace": workspace})

        self.assertIs(result, account)
        stored = account["state"]["workspace"]
        self.assertEqual(stored["saved"], ["script-a", "script-b"])
        self.assertEqual(set(stored["selection_times"]), {"script-a", "script-b"})
        save_accounts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
