import unittest
from unittest.mock import patch

import app


class AdminAccountActivationTests(unittest.TestCase):
    def test_admin_created_account_is_immediately_registered(self) -> None:
        saved = []
        with (
            patch.object(app, "load_accounts", return_value=[]),
            patch.object(app, "save_accounts", side_effect=lambda accounts: saved.extend(accounts)),
        ):
            account = app.upsert_account(
                "551199887766",
                source="admin_created",
                phone="551199887766",
            )

        self.assertEqual(account["registration_status"], "registered")
        self.assertEqual(account["source"], "admin_created")
        self.assertEqual(account["phone"], "551199887766")
        self.assertEqual(saved[0]["registration_status"], "registered")
        self.assertTrue(app.valid_creator_login_password(saved[0], "551199887766", "7766"))

    def test_admin_created_existing_account_becomes_registered(self) -> None:
        existing = {
            "account_id": "551199887766",
            "phone": "551199887766",
            "login_aliases": ["551199887766"],
            "registration_status": "unregistered",
            "status": "active",
        }
        saved = []
        with (
            patch.object(app, "load_accounts", return_value=[existing]),
            patch.object(app, "save_accounts", side_effect=lambda accounts: saved.extend(accounts)),
        ):
            account = app.upsert_account("551199887766", source="admin_created")

        self.assertEqual(account["registration_status"], "registered")
        self.assertTrue(account["registered_at"])
        self.assertEqual(saved[0]["registration_status"], "registered")


if __name__ == "__main__":
    unittest.main()
