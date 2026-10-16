import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PublicSignupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.patches = [
            patch.object(app, "ACCOUNTS_FILE", root / "creator_accounts.json"),
            patch.object(app, "CREATORS_FILE", root / "creator_profiles.json"),
            patch.object(app, "SUBMISSIONS_FILE", root / "creator_submissions.json"),
        ]
        for item in self.patches:
            item.start()
        app.ACCOUNTS_CACHE.update(signature=None, accounts=[])

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        app.ACCOUNTS_CACHE.update(signature=None, accounts=[])
        self.directory.cleanup()

    def test_signup_creates_account_and_creator_card_without_changing_legacy_login(self) -> None:
        legacy = app.find_account("666")
        self.assertTrue(app.valid_creator_login_password(legacy, "666", "666"))
        account, profile = app.register_public_creator({
            "phone": "5511999876543",
            "password": "long-secret-password",
            "kwai_url": "https://www.kwai.com/@new.creator",
        })
        self.assertEqual(profile["account_id"], account["account_id"])
        self.assertEqual(profile["kwai_id"], "new.creator")
        self.assertEqual(profile["profile_sync_status"], "pending")
        self.assertTrue(app.valid_creator_login_password(account, account["phone"], "long-secret-password"))
        self.assertFalse(app.valid_creator_login_password(account, account["phone"], "6543"))
        self.assertNotIn("password_hash", app.public_account(account))
        self.assertEqual(app.find_account("new.creator")["account_id"], account["account_id"])
        self.assertTrue(any(item["profile_id"] == profile["profile_id"] for item in app.public_creator_profiles()))
        self.assertTrue(app.valid_creator_login_password(app.find_account("666"), "666", "666"))

    def test_duplicate_phone_or_kwai_profile_never_merges_accounts(self) -> None:
        app.register_public_creator({"phone": "5511999876543", "password": "long-secret-password", "kwai_url": "https://kwai.com/@new.creator"})
        with self.assertRaises(FileExistsError):
            app.register_public_creator({"phone": "5511999876543", "password": "another-password", "kwai_url": "https://kwai.com/@second.creator"})
        with self.assertRaises(FileExistsError):
            app.register_public_creator({"phone": "5511988876543", "password": "another-password", "kwai_url": "https://kwai.com/@new.creator"})
        self.assertEqual(len([item for item in app.load_creator_profiles() if item.get("source") == "self_signup" or item.get("kwai_id") == "new.creator"]), 1)

    def test_rejects_bad_password_and_non_kwai_urls(self) -> None:
        for url in ("http://www.kwai.com/@creator", "https://evil.example/@creator", "https://www.kwai.com.evil.example/@creator", "https://www.kwai.com/video/123"):
            with self.assertRaises(ValueError):
                app.register_public_creator({"phone": "5511999876543", "password": "long-secret-password", "kwai_url": url})
        with self.assertRaises(ValueError):
            app.register_public_creator({"phone": "5511999876543", "password": "1234", "kwai_url": "https://www.kwai.com/@creator"})

    def test_kwai_generic_page_does_not_become_a_creator_name(self) -> None:
        generic_page = '<meta property="og:title" content="kwai-nuxt-pwa-pc"><meta property="og:description" content="Make Everyone Shine">'
        with patch.object(app, "fetch_text", return_value=generic_page):
            profile = app.fetch_kwai_profile("https://www.kwai.com/@missing.creator")
        self.assertEqual(profile["name"], "missing.creator")
        self.assertFalse(profile["profile_found"])
        self.assertFalse(profile["bio"])

    def test_link_entry_creates_one_account_and_creator_card(self) -> None:
        account, profile, created = app.enter_by_kwai_profile("https://www.kwai.com/@new.creator")
        self.assertTrue(created)
        self.assertEqual(profile["account_id"], account["account_id"])
        self.assertEqual(profile["kwai_url"], "https://www.kwai.com/@new.creator")
        self.assertEqual(profile["profile_sync_status"], "pending")
        self.assertEqual(account["registration_status"], "registered")
        self.assertTrue(any(item["profile_id"] == profile["profile_id"] for item in app.public_creator_profiles()))
        again, same_profile, created_again = app.enter_by_kwai_profile("https://kwai.com/@new.creator")
        self.assertFalse(created_again)
        self.assertEqual(again["account_id"], account["account_id"])
        self.assertEqual(same_profile["profile_id"], profile["profile_id"])
        self.assertEqual(len(app.load_creator_profiles()), 1)

    def test_link_entry_reuses_legacy_account_and_history(self) -> None:
        legacy = app.upsert_account("5511999000000", kwai_id="legacy.creator", source="admin")
        app.update_account_state(legacy["account_id"], {"preferences_completed": True})
        app.save_creator_profiles([{
            "profile_id": "legacy-profile", "account_id": legacy["account_id"],
            "kwai_id": "legacy.creator", "kwai_url": "https://kwai.com/@legacy.creator",
            "name": "Legacy Creator", "created_at": app.now_iso(),
        }])
        app.write_json_atomic(app.SUBMISSIONS_FILE, [{"creator_id": legacy["account_id"], "entry_id": "script-1", "video_url": "https://www.kwai.com/@legacy.creator/video/1"}])
        account, profile, created = app.enter_by_kwai_profile("https://www.kwai.com/@legacy.creator")
        self.assertFalse(created)
        self.assertEqual(account["account_id"], legacy["account_id"])
        self.assertEqual(profile["profile_id"], "legacy-profile")
        self.assertTrue(app.find_account(legacy["account_id"])["state"]["preferences_completed"])
        self.assertEqual(len(app.public_account(account)["submissions"]), 1)
        self.assertEqual(len(app.load_creator_profiles()), 1)

    def test_link_entry_finds_legacy_account_through_profile_phone(self) -> None:
        legacy = app.upsert_account("5511999000001", source="admin")
        app.save_creator_profiles([{
            "profile_id": "phone-linked-profile", "account_id": "old-profile-id",
            "phone": legacy["account_id"], "kwai_id": "legacy.by.phone",
            "kwai_url": "https://kwai.com/@legacy.by.phone", "created_at": app.now_iso(),
        }])
        account, profile, created = app.enter_by_kwai_profile("https://kwai.com/@legacy.by.phone")
        self.assertFalse(created)
        self.assertEqual(account["account_id"], legacy["account_id"])
        self.assertEqual(profile["account_id"], legacy["account_id"])

    def test_link_entry_reuses_card_linked_only_by_account_id(self) -> None:
        legacy = app.upsert_account("5511999000002", kwai_id="legacy.no.card.id", source="admin")
        app.save_creator_profiles([{
            "profile_id": "account-linked-card", "account_id": legacy["account_id"],
            "name": "Legacy Creator", "created_at": app.now_iso(),
        }])
        account, profile, created = app.enter_by_kwai_profile("https://kwai.com/@legacy.no.card.id")
        self.assertFalse(created)
        self.assertEqual(account["account_id"], legacy["account_id"])
        self.assertEqual(profile["profile_id"], "account-linked-card")
        self.assertEqual(len(app.load_creator_profiles()), 1)

    def test_link_entry_rejects_non_profile_urls(self) -> None:
        for url in (
            "", "hello", "https://evil.example/@creator", "http://kwai.com/@creator",
            "https://kwai.com/video/123", "https://kwai.com/@creator/video/123",
            "https://kwai.com.evil.example/@creator", "https://kwai.com:abc/@creator",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                app.enter_by_kwai_profile(url)
        self.assertFalse(app.load_creator_profiles())

    def test_login_attempts_are_limited_per_account_and_source(self) -> None:
        app.AUTH_ATTEMPTS.clear()
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertFalse(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-b", limit=2, window=900))
        app.AUTH_ATTEMPTS.clear()


if __name__ == "__main__":
    unittest.main()
