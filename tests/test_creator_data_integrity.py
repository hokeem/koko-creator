import tempfile
import json
import http.client
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import app


class CreatorDataIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.patches = [
            patch.object(app, "ACCOUNTS_FILE", root / "creator_accounts.json"),
            patch.object(app, "CREATORS_FILE", root / "creator_profiles.json"),
            patch.object(app, "SUBMISSIONS_FILE", root / "creator_submissions.json"),
            patch.object(app, "ANALYTICS_FILE", root / "creator_analytics_events.json"),
        ]
        for item in self.patches:
            item.start()
        app.ACCOUNTS_CACHE.update(signature=None, accounts=[])

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        app.ACCOUNTS_CACHE.update(signature=None, accounts=[])
        self.directory.cleanup()

    def test_one_hundred_creators_register_and_update_without_overwriting(self) -> None:
        handles = [f"creator_{index:03d}" for index in range(100)]
        with ThreadPoolExecutor(max_workers=30) as pool:
            created = list(pool.map(lambda handle: app.enter_by_kwai_profile(f"https://kwai.com/@{handle}"), handles))
        ids = {account["account_id"] for account, _, _ in created}
        self.assertEqual(len(ids), 100)
        self.assertEqual(len([profile for profile in app.load_creator_profiles() if profile.get("kwai_id") in handles]), 100)

        with ThreadPoolExecutor(max_workers=30) as pool:
            list(pool.map(lambda item: app.update_account_state(item[0][0]["account_id"], {"preferences": {"handle": item[1]}}), zip(created, handles)))
        for account, handle in zip((item[0] for item in created), handles):
            self.assertEqual(app.find_account(account["account_id"])["state"]["preferences"]["handle"], handle)

    def test_campaign_cookie_is_signed_and_attribution_survives_reentry(self) -> None:
        touch = {"source": "email", "campaign": "october", "at": app.now_iso()}
        cookie = app.campaign_cookie_header(touch)[1].split(";", 1)[0]
        self.assertEqual(app.campaign_touch_from_headers({"Cookie": cookie}), {"first": touch, "last": touch})
        self.assertIsNone(app.campaign_touch_from_headers({"Cookie": cookie[:-1] + "x"}))
        account, _, _ = app.enter_by_kwai_profile("https://kwai.com/@campaign_creator", {"first": touch, "last": touch})
        second = {"source": "instagram", "campaign": "reels", "at": app.now_iso()}
        account, _, _ = app.enter_by_kwai_profile("https://kwai.com/@campaign_creator", {"first": touch, "last": second})
        self.assertEqual(account["attribution"]["first"], touch)
        self.assertEqual(account["attribution"]["last"], second)
        app.persist_analytics_events([
            {"event": "script_open", "script_id": "a" * 32, "account_id": account["account_id"], "created_at": app.now_iso()},
            {"event": "save_click", "account_id": account["account_id"], "created_at": app.now_iso()},
        ])
        app.write_json_atomic(app.SUBMISSIONS_FILE, [
            {"creator_id": account["account_id"], "created_at": app.now_iso(), "video_url": "https://kwai.com/video/1"}
        ])
        dashboard = app.creator_campaign_dashboard_payload(30)
        self.assertEqual(len(dashboard["rows"]), 1)
        self.assertEqual(dashboard["rows"][0]["new_creators"], 1)
        self.assertEqual(dashboard["rows"][0]["active_creators"], 1)
        self.assertEqual(dashboard["rows"][0]["script_opens"], 1)
        self.assertEqual(dashboard["rows"][0]["submissions"], 1)

    def test_campaign_link_redirect_and_dashboard(self) -> None:
        server = app.ResilientThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            with patch.object(app.Handler, "log_message"):
                connection.request("GET", "/go/email/october")
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 302)
                self.assertEqual(response.getheader("Location"), "/")
                cookies = response.headers.get_all("Set-Cookie") or []
                self.assertEqual(len(cookies), 2)
                self.assertTrue(any(app.ATTRIBUTION_COOKIE in item for item in cookies))
                cookie_header = "; ".join(item.split(";", 1)[0] for item in cookies)
                with patch.object(app, "schedule_profile_enrichment"):
                    connection.request(
                        "POST", "/api/auth/kwai-link",
                        body=json.dumps({"kwai_url": "https://www.kwai.com/@tracked_creator"}),
                        headers={"Content-Type": "application/json", "Cookie": cookie_header},
                    )
                    entered = connection.getresponse()
                    entered.read()
                    self.assertEqual(entered.status, 200)
                connection.request("GET", "/go/email/bad%2Fpath")
                invalid = connection.getresponse()
                invalid.read()
                self.assertEqual(invalid.status, 404)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        dashboard = app.creator_campaign_dashboard_payload(30)
        self.assertEqual(dashboard["summary"]["visits"], 1)
        self.assertEqual(dashboard["summary"]["new_creators"], 1)
        self.assertEqual(dashboard["rows"][0]["source"], "email")

    def test_one_hundred_simultaneous_http_entries_keep_cards_and_activity(self) -> None:
        app.AUTH_ATTEMPTS.clear()
        server = app.ResilientThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def enter(index: int) -> int:
            payload = json.dumps({"kwai_url": f"https://www.kwai.com/@http_creator_{index:03d}"}).encode()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
            try:
                connection.request("POST", "/api/auth/kwai-link", body=payload, headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, body[:300])
                self.assertTrue(json.loads(body)["ok"])
                return response.status
            finally:
                connection.close()

        try:
            with patch.object(app, "schedule_profile_enrichment"), patch.object(app.Handler, "log_message"):
                with ThreadPoolExecutor(max_workers=100) as pool:
                    statuses = list(pool.map(enter, range(100)))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.assertEqual(statuses, [200] * 100)
        self.assertEqual(len([item for item in app.load_creator_profiles() if str(item.get("kwai_id", "")).startswith("http_creator_")]), 100)
        summary = app.creator_analytics_summary_payload(days=7)
        self.assertEqual(summary["summary"]["weekly_active_users"], 100)

    def test_concurrent_submissions_are_not_lost_or_duplicated(self) -> None:
        script_id = "a" * 32
        with (
            patch.object(app, "entry_by_id", return_value={"entry_id": script_id, "title": "Test"}),
            patch.object(app, "link_metadata", return_value={}),
            patch.object(app, "resolve_kwai_id_from_video_link", return_value=""),
        ):
            with ThreadPoolExecutor(max_workers=30) as pool:
                submitted = list(pool.map(
                    lambda index: app.save_submission({"entry_id": script_id, "video_url": f"https://www.kwai.com/@creator_{index:03d}/video/{index}"}, account={"account_id": f"creator_{index:03d}"}),
                    range(100),
                ))
        self.assertEqual(len({item["submission_id"] for item in submitted}), 100)
        self.assertEqual(len(app.read_json_file(app.SUBMISSIONS_FILE, [])), 100)

    def test_submissions_are_not_truncated_after_one_thousand(self) -> None:
        script_id = "b" * 32
        existing = [{"submission_id": str(index), "creator_id": f"old_{index}", "video_url": f"https://kwai.com/video/{index}"} for index in range(1000)]
        app.write_json_atomic(app.SUBMISSIONS_FILE, existing)
        with (
            patch.object(app, "entry_by_id", return_value={"entry_id": script_id, "title": "Test"}),
            patch.object(app, "link_metadata", return_value={}),
            patch.object(app, "resolve_kwai_id_from_video_link", return_value=""),
        ):
            app.save_submission({"entry_id": script_id, "video_url": "https://www.kwai.com/@new_creator/video/1001"}, account={"account_id": "new_creator"})
        self.assertEqual(len(app.read_json_file(app.SUBMISSIONS_FILE, [])), 1001)

    def test_analytics_acknowledgement_is_durable_and_concurrent(self) -> None:
        with ThreadPoolExecutor(max_workers=30) as pool:
            list(pool.map(lambda index: app.enqueue_analytics_events([{"event_id": str(index), "event": "save_click"}]), range(100)))
        self.assertEqual(len(app.load_analytics_events()), 100)
        with patch.object(app, "append_analytics_log", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.enqueue_analytics_events([{"event_id": "failed"}])

    def test_corrupt_creator_file_is_not_replaced_by_an_empty_list(self) -> None:
        app.SUBMISSIONS_FILE.write_text("{broken", "utf-8")
        with (
            patch.object(app, "entry_by_id", return_value={"entry_id": "a" * 32, "title": "Test"}),
            patch.object(app, "link_metadata", return_value={}),
            patch.object(app, "resolve_kwai_id_from_video_link", return_value=""),
        ):
            with self.assertRaises(ValueError):
                app.save_submission({"entry_id": "a" * 32, "video_url": "https://kwai.com/@creator/video/1"}, account={"account_id": "creator"})
        self.assertEqual(app.SUBMISSIONS_FILE.read_text("utf-8"), "{broken")

    def test_prune_preserves_newer_events_and_rejects_corrupt_log(self) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        app.persist_analytics_events([{"event_id": "first", "event": "login", "created_at": stamp}])
        app.prune_analytics_events(retention_days=7, max_events=10)
        app.persist_analytics_events([{"event_id": "second", "event": "save_click", "created_at": stamp}])
        self.assertEqual([event["event_id"] for event in app.load_analytics_events()], ["first", "second"])
        path = app.analytics_log_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write("not-json\n")
        with self.assertRaises(ValueError):
            app.prune_analytics_events(retention_days=7, max_events=10)
        self.assertIn("not-json\n", path.read_text("utf-8"))

    def test_weekly_activity_counts_any_action_once_per_account_and_day(self) -> None:
        first = app.upsert_account("creator_a", kwai_id="creator_a")
        second = app.upsert_account("creator_b", kwai_id="creator_b")
        stamp = datetime.now(timezone.utc).isoformat()
        events = [
            {"event_id": "1", "event": "login", "created_at": stamp, "account_id": first["account_id"], "visitor_id": "shared"},
            {"event_id": "2", "event": "save_click", "created_at": stamp, "account_id": first["account_id"], "visitor_id": "shared", "script_id": "a" * 32},
            {"event_id": "3", "event": "page_duration", "created_at": stamp, "account_id": second["account_id"], "visitor_id": "shared"},
        ]
        app.persist_analytics_events(events)
        summary = app.creator_analytics_summary_payload(days=7)
        self.assertEqual(summary["summary"]["weekly_active_users"], 1)
        self.assertEqual(summary["summary"]["daily_active_users"], 1)
        today = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        self.assertEqual(summary["daily_usage"][0]["day"], today)
        self.assertEqual(summary["daily_usage"][0]["active_users"], 1)

        with patch.object(app, "script_title_for_id", return_value="Test"):
            detail = app.creator_analytics_payload(days=7)
        rows = {item["account_id"]: item for item in detail["users"]}
        self.assertEqual(rows[first["account_id"]]["click_counts"].get("save_click"), 1)
        self.assertNotIn("save_click", rows[second["account_id"]]["click_counts"])

    def test_unique_script_count_is_not_limited_to_preview_rows(self) -> None:
        account = app.upsert_account("creator_c", kwai_id="creator_c")
        stamp = datetime.now(timezone.utc).isoformat()
        app.persist_analytics_events([
            {"event_id": str(index), "event": "detail_open", "created_at": stamp, "account_id": account["account_id"], "script_id": f"{index:032x}"}
            for index in range(25)
        ])
        with patch.object(app, "script_title_for_id", return_value="Test"):
            detail = app.creator_analytics_payload(days=7)
        row = next(item for item in detail["users"] if item["account_id"] == account["account_id"])
        self.assertEqual(row["unique_scripts_opened"], 25)
        self.assertEqual(len(row["script_views"]), 20)
