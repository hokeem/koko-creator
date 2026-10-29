import unittest
from unittest.mock import patch

import app


class DashboardSummaryTests(unittest.TestCase):
    def test_all_script_views_and_attribution_are_included(self):
        account = {"account_id": "creator-a", "registration_status": "registered",
                   "attribution": {"first": {"source": "inbox"}}}
        test_account = {"account_id": "666"}
        events = [{"event": "script_open", "account_id": "creator-a",
                   "script_id": str(i), "created_at": app.now_iso()} for i in range(25)]
        events.append({"event": "script_open", "account_id": "666",
                       "script_id": "test", "created_at": app.now_iso()})
        with (patch.object(app, "load_accounts", return_value=[account, test_account]),
              patch.object(app, "load_analytics_events", return_value=events),
              patch.object(app, "read_json_file", return_value=[]),
              patch.object(app, "load_creator_profiles", return_value=[])):
            result = app.creator_analytics_summary_payload(30)
        self.assertEqual(result["summary"]["script_opens"], 25)
        self.assertEqual(len(result["users"]), 1)
        self.assertEqual(result["users"][0]["source"], "inbox")
        self.assertEqual(len(result["users"][0]["script_views"]), 25)


if __name__ == "__main__":
    unittest.main()
