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

    def test_login_attempts_are_limited_per_account_and_source(self) -> None:
        app.AUTH_ATTEMPTS.clear()
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertFalse(app.auth_rate_allowed("login", "test-ip:account-a", limit=2, window=900))
        self.assertTrue(app.auth_rate_allowed("login", "test-ip:account-b", limit=2, window=900))
        app.AUTH_ATTEMPTS.clear()


if __name__ == "__main__":
    unittest.main()
