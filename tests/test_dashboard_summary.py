import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import app


class DashboardSummaryTests(unittest.TestCase):
    def test_recommendation_actions_count_toward_the_clicked_script(self):
        clicked_id = "a" * 32
        previous_id = "b" * 32
        account = {"account_id": "creator-a", "registration_status": "registered"}
        events = [
            app.build_analytics_event(
                {"event": name, "script_id": previous_id, "meta": {"script_id": clicked_id}},
                {}, account=account,
            )
            for name in ("featured_detail_open", "daily_plan_add", "daily_script_skip", "feature_video_play")
        ]
        self.assertTrue(all(event["script_id"] == clicked_id for event in events))
        # Older skip events could inherit the last detail's ID from the page.
        events.append({"event": "daily_script_skip", "script_id": previous_id,
                       "account_id": "creator-a", "created_at": app.now_iso()})
        with (patch.object(app, "load_accounts", return_value=[account]),
              patch.object(app, "load_analytics_events", return_value=events),
              patch.object(app, "read_json_file", return_value=[]),
              patch.object(app, "load_creator_profiles", return_value=[])):
            result = app.creator_analytics_summary_payload(7, beijing_calendar=True)
        self.assertEqual(result["summary"]["script_opens"], 4)
        self.assertEqual(result["users"][0]["script_share_open_count"], 4)
        self.assertEqual(result["users"][0]["script_views"], [{"script_id": clicked_id, "views": 4}])
        self.assertEqual(result["historical_script_opened_ids"], [clicked_id])

    def test_all_time_includes_events_older_than_rolling_window(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        account = {"account_id": "creator-a", "registration_status": "registered"}
        events = [{"event": "script_open", "account_id": "creator-a", "script_id": "old", "created_at": old}]
        with (patch.object(app, "load_accounts", return_value=[account]),
              patch.object(app, "load_analytics_events", return_value=events),
              patch.object(app, "read_json_file", return_value=[]),
              patch.object(app, "load_creator_profiles", return_value=[])):
            rolling = app.creator_analytics_summary_payload(7, beijing_calendar=True)
            all_time = app.creator_analytics_summary_payload(7, all_time=True)
        self.assertEqual(rolling["summary"]["script_opens"], 0)
        self.assertEqual(all_time["summary"]["script_opens"], 1)
        self.assertEqual(all_time["period_mode"], "all")

    def test_campaign_all_time_includes_old_visits(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        event = {"event": "campaign_visit", "created_at": old, "visitor_id": "visitor-1", "user_agent": "Mozilla/5.0", "meta": {"source": "inbox", "campaign": "default"}}
        with (patch.object(app, "load_accounts", return_value=[]),
              patch.object(app, "load_analytics_events", return_value=[event]),
              patch.object(app, "read_json_file", return_value=[])):
            rolling = app.creator_campaign_dashboard_payload(7)
            all_time = app.creator_campaign_dashboard_payload(7, all_time=True)
        self.assertEqual(sum(row["visits"] for row in rolling["rows"]), 0)
        self.assertEqual(sum(row["visits"] for row in all_time["rows"]), 1)

    def test_beijing_calendar_uses_complete_calendar_days(self):
        now = datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai'))
        start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        account = {'account_id': 'creator-a'}
        events = [
            {'event': 'script_open', 'account_id': 'creator-a', 'script_id': 'inside', 'created_at': start.isoformat()},
            {'event': 'script_open', 'account_id': 'creator-a', 'script_id': 'outside', 'created_at': (start - timedelta(seconds=1)).isoformat()},
        ]
        with (patch.object(app, 'load_accounts', return_value=[account]),
              patch.object(app, 'load_analytics_events', return_value=events),
              patch.object(app, 'read_json_file', return_value=[]),
              patch.object(app, 'load_creator_profiles', return_value=[])):
            result = app.creator_analytics_summary_payload(7, beijing_calendar=True)
        self.assertEqual(result['summary']['script_opens'], 1)
        self.assertEqual(result['users'][0]['script_views'][0]['script_id'], 'inside')

    def test_all_script_views_and_attribution_are_included(self):
        account = {"account_id": "creator-a", "registration_status": "registered",
                   "attribution": {"first": {"source": "inbox"}}}
        test_account = {"account_id": "666"}
        events = [{"event": "script_open", "account_id": "creator-a",
                   "script_id": str(i), "created_at": app.now_iso()} for i in range(25)]
        events.append({"event": "script_open", "account_id": "666",
                       "script_id": "test", "created_at": app.now_iso()})
        events.extend([
            {"event": "page_duration", "account_id": "creator-a", "page_type": "script",
             "script_id": "0", "duration_ms": 2500, "created_at": app.now_iso()},
            {"event": next(iter(app.CLICK_EVENT_LABELS)), "account_id": "creator-a", "created_at": app.now_iso()},
        ])
        with (patch.object(app, "load_accounts", return_value=[account, test_account]),
              patch.object(app, "load_analytics_events", return_value=events),
              patch.object(app, "read_json_file", return_value=[]),
              patch.object(app, "load_creator_profiles", return_value=[])):
            result = app.creator_analytics_summary_payload(30)
        self.assertEqual(result["summary"]["script_opens"], 25)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["source"], "inbox")
        self.assertEqual(len(result["users"][0]["script_views"]), 25)
        self.assertEqual(result["users"][0]["script_duration_seconds"], 2.5)
        self.assertEqual(sum(result["users"][0]["click_counts"].values()), 1)
        self.assertIn("0", result["historical_script_opened_ids"])
        self.assertTrue(result["history_start"])


if __name__ == "__main__":
    unittest.main()
