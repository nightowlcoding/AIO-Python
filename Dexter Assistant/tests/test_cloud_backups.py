from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

import test_data_exports
from test_data_exports import _dexter


CLOUD_ENV = {
    "DEXTER_TOKEN_ENC_KEY": Fernet.generate_key().decode("ascii"),
    "GOOGLE_OAUTH_CLIENT_ID": "gid",
    "GOOGLE_OAUTH_CLIENT_SECRET": "gsecret",
}


class CloudBackupTests(unittest.TestCase):
    setUp = test_data_exports.DataExportTests.setUp
    tearDown = test_data_exports.DataExportTests.tearDown
    _login = test_data_exports.DataExportTests._login
    _wait_for_jobs = test_data_exports.DataExportTests._wait_for_jobs

    def _connect_google(self) -> None:
        self._login(self.super_admin, "Super Admin", self.alpha)
        start = self.client.post("/admin/backups/cloud/connect/google")
        self.assertEqual(start.status_code, 302)
        query = parse_qs(urlparse(start.headers["Location"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("drive.file", query["scope"][0])
        tokens = {"refresh_token": "plain-refresh", "access_token": "a", "account_email": "owner@alpha.test"}
        with patch.object(_dexter.dexter_cloud, "exchange_code", return_value=tokens), patch.object(
            _dexter.dexter_cloud, "google_ensure_folder", return_value="folder-1"
        ):
            done = self.client.get(f"/admin/backups/cloud/callback/google?state={query['state'][0]}&code=abc")
        self.assertIn("message=", done.headers["Location"])

    def test_connect_stores_encrypted_token_and_rejects_bad_state(self) -> None:
        with patch.dict(os.environ, CLOUD_ENV):
            self._login(self.super_admin, "Super Admin", self.alpha)
            self.client.post("/admin/backups/cloud/connect/google")
            forged = self.client.get("/admin/backups/cloud/callback/google?state=forged&code=abc")
            self.assertIn("error=", forged.headers["Location"])
            self.assertIsNone(_dexter._get_backup_destination(self.alpha))

            self._connect_google()
            stored = _dexter._get_backup_destination(self.alpha, include_secret=True)
            self.assertEqual(stored["account_email"], "owner@alpha.test")
            self.assertNotIn("plain-refresh", stored["enc_refresh_token"])
            self.assertEqual(_dexter.dexter_cloud.decrypt_token(stored["enc_refresh_token"]), "plain-refresh")
            self.assertIsNone(_dexter._get_backup_destination(self.beta))

    def test_cloud_backup_success_and_failure_are_recorded(self) -> None:
        with patch.dict(os.environ, CLOUD_ENV):
            self._connect_google()
            uploaded = {"refresh_token": "rotated", "folder_id": "folder-1", "file_id": "f", "pruned": 0, "folder_name": "x"}
            with patch.object(_dexter.dexter_cloud, "upload_backup", return_value=uploaded) as upload, patch.object(
                _dexter, "_notify_backup_admins"
            ):
                self.client.post("/admin/backups/cloud/run")
                self._wait_for_jobs()
            self.assertEqual(upload.call_args.args[1], "plain-refresh")
            stored = _dexter._get_backup_destination(self.alpha, include_secret=True)
            self.assertTrue(stored["last_upload_at"])
            self.assertEqual(_dexter.dexter_cloud.decrypt_token(stored["enc_refresh_token"]), "rotated")
            self.assertEqual(_dexter._overdue_company_backups()[0]["name"], "Beta Co")

            with patch.object(
                _dexter.dexter_cloud, "upload_backup", side_effect=_dexter.dexter_cloud.CloudError("token revoked")
            ), patch.object(_dexter, "_notify_backup_admins") as notify:
                self.client.post("/admin/backups/cloud/run")
                self._wait_for_jobs()
            self.assertIn("token revoked", _dexter._get_backup_destination(self.alpha)["last_error"])
            self.assertIn("FAILED", notify.call_args.args[0])

    def test_sweep_reminds_once_for_companies_without_cloud(self) -> None:
        with patch.object(_dexter, "_notify_backup_admins") as notify:
            _dexter._run_company_backup_sweep()
            _dexter._run_company_backup_sweep()
        subjects = [c.args[0] for c in notify.call_args_list]
        self.assertEqual(len(subjects), len(set(subjects)))
        self.assertIn("Reminder: back up Alpha Co", subjects)
        self.assertIn("Reminder: back up Beta Co", subjects)

    def test_disconnect_and_manager_forbidden(self) -> None:
        with patch.dict(os.environ, CLOUD_ENV):
            self._connect_google()
            with patch.object(_dexter.dexter_cloud, "revoke") as revoke:
                self.client.post("/admin/backups/cloud/disconnect")
            revoke.assert_called_once_with("google", "plain-refresh")
            self.assertIsNone(_dexter._get_backup_destination(self.alpha))
            self._login(self.manager, "Manager", self.alpha)
            self.assertEqual(self.client.post("/admin/backups/cloud/connect/google").status_code, 403)


if __name__ == "__main__":
    unittest.main()
