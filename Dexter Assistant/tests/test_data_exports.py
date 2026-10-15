from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from _dexter_test_harness import load_dexter_module


_dexter = load_dexter_module()


class DataExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        _dexter.RBAC_DB_PATH = tmp / "rbac_test.db"
        # get_rbac_db_connection caches the first verified path; force it onto the temp DB.
        _dexter._RBAC_DB_PATH_VERIFIED = None
        _dexter.app.config["TESTING"] = True
        _dexter.app.config["WTF_CSRF_ENABLED"] = False
        _dexter.initialize_rbac_db()
        _dexter.migrate_add_task_fields_v1()
        _dexter.migrate_add_password_reset_fields_v1()
        _dexter.migrate_add_company_scope_v1()
        _dexter.migrate_add_login_lockout_fields_v1()
        _dexter.migrate_add_company_profiles_v1()
        _dexter.migrate_add_company_email_settings_v1()
        _dexter.migrate_add_user_location_assignments_v1()
        _dexter.migrate_add_company_deletion_v1()

        conn = _dexter.get_rbac_db_connection()
        try:
            roles = {r["name"]: int(r["id"]) for r in conn.execute("SELECT id, name FROM roles")}
            self.alpha = int(conn.execute("INSERT INTO companies (name, slug, is_active) VALUES ('Alpha Co', 'alpha-co', 1)").lastrowid)
            self.beta = int(conn.execute("INSERT INTO companies (name, slug, is_active) VALUES ('Beta Co', 'beta-co', 1)").lastrowid)
            insert_user = "INSERT INTO users (username, password_hash, role_id, company_id, is_active) VALUES (?, 'secret-hash', ?, ?, 1)"
            self.super_admin = int(conn.execute(insert_user, ("sa@example.com", roles["Super Admin"], self.alpha)).lastrowid)
            self.manager = int(conn.execute(insert_user, ("mgr_alpha", roles["Manager"], self.alpha)).lastrowid)
            conn.execute(insert_user, ("emp_beta", roles["Employee"], self.beta))
            conn.commit()
        finally:
            conn.close()

        self.storage = tmp / "company_data"
        (self.storage / f"company_{self.alpha}" / "profile").mkdir(parents=True)
        (self.storage / f"company_{self.alpha}" / "profile" / "alpha.txt").write_text("alpha")
        (self.storage / f"company_{self.beta}" / "profile").mkdir(parents=True)
        (self.storage / f"company_{self.beta}" / "profile" / "beta.txt").write_text("beta")

        paths = {
            "persistent_root": tmp,
            "company_data_path": tmp / "mgr_company_data",
            "db_path": tmp / "missing_manager.db",
            "ic3_data_path": tmp / "ic3",
            "daily_logs_root": tmp / "legacy" / "daily_logs",
            "uploads_root": tmp / "legacy" / "uploads",
            "order_invoices_root": tmp / "legacy" / "OrderInvoices",
            "inventory_data_root": tmp / "legacy" / "inventory_data",
            "reports_root": tmp / "legacy" / "reports",
        }
        (tmp / "legacy" / "daily_logs").mkdir(parents=True)
        (tmp / "legacy" / "daily_logs" / "2025-11-07_Day.csv").write_text("day")
        (tmp / "legacy" / "daily_logs" / "2025-11-08_Day.csv").write_text("day2")
        self.pm_db = tmp / "pm.db"
        pm = sqlite3.connect(self.pm_db)
        pm.executescript(
            """
            CREATE TABLE restaurants (id INTEGER PRIMARY KEY, name TEXT, location TEXT, city TEXT, state TEXT);
            INSERT INTO restaurants VALUES (1, 'Alpha Co', 'Alice', '', ''), (2, 'Beta Co', 'Kingsville', '', '');
            CREATE TABLE product_mix_uploads (id INTEGER PRIMARY KEY, restaurant_id INTEGER, filename TEXT);
            INSERT INTO product_mix_uploads VALUES (10, 1, 'alpha.csv'), (20, 2, 'beta.csv');
            """
        )
        pm.commit()
        pm.close()
        self.ic3 = tmp / "ic3"
        self.ic3.mkdir()
        (self.ic3 / "inventory_database.json").write_text(
            json.dumps({"Alice": {"2026-01-01": {"P1": 5}}, "Kingsville": {"2026-01-01": {"P1": 9}}})
        )
        self.patches = [
            patch.object(_dexter, "COMPANY_STORAGE_ROOT", self.storage),
            patch.object(_dexter, "_manager_backup_paths", lambda: paths),
            patch.object(_dexter, "_productmix_db_path", lambda: self.pm_db),
            patch.dict(os.environ, {"DEXTER_EXPORTS_DIR": str(tmp / "exports")}),
        ]
        for p in self.patches:
            p.start()
        self.client = _dexter.app.test_client()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _login(self, user_id: int, role: str, company_id: int) -> None:
        with self.client.session_transaction() as sess:
            sess[_dexter.SESSION_USER_KEY] = {
                "username": f"user_{user_id}",
                "user_id": user_id,
                "role_name": role,
                "company_id": company_id,
                "selected_company_id": company_id,
                "is_admin": role == "Super Admin",
            }

    def test_manager_cannot_export_or_download(self) -> None:
        self._login(self.manager, "Manager", self.alpha)
        self.assertEqual(self.client.post("/admin/exports/company").status_code, 403)
        self.assertEqual(self.client.post("/admin/exports/system").status_code, 403)
        self.assertEqual(self.client.get("/admin/exports/download/company/x.zip").status_code, 403)

    def test_company_export_contains_only_selected_company(self) -> None:
        self._login(self.super_admin, "Super Admin", self.alpha)
        result = _dexter._build_company_export(self.alpha, self.super_admin, "tester")

        page = self.client.get("/admin/company-profile")
        self.assertEqual(page.status_code, 200)
        self.assertIn(result["file"], page.get_data(as_text=True))

        response = self.client.get(f"/admin/exports/download/company/{result['file']}")
        self.assertEqual(response.status_code, 200)
        data = response.data
        response.close()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            users_csv = zf.read("data/dexter/users.csv").decode("utf-8-sig")
        self.assertIn("files/dexter/profile/alpha.txt", names)
        self.assertNotIn("files/dexter/profile/beta.txt", names)
        self.assertIn("manifest.json", names)
        self.assertIn("mgr_alpha", users_csv)
        self.assertNotIn("emp_beta", users_csv)
        self.assertNotIn("secret-hash", users_csv)
        self.assertNotIn("password_hash", users_csv)

    def test_other_company_exports_are_not_reachable(self) -> None:
        self._login(self.super_admin, "Super Admin", self.beta)
        beta_file = _dexter._build_company_export(self.beta, self.super_admin, "tester")["file"]
        self._login(self.super_admin, "Super Admin", self.alpha)
        self.assertEqual(self.client.get(f"/admin/exports/download/company/{beta_file}").status_code, 404)
        self.assertEqual(self.client.get("/admin/exports/download/company/..%2F..%2Fsecret.zip").status_code, 404)
        self.assertEqual(self.client.get("/admin/exports/download/other/x.zip").status_code, 404)

    def _export_path(self, company_id: int) -> Path:
        name = _dexter._build_company_export(company_id, self.super_admin, "tester")["file"]
        return Path(os.environ["DEXTER_EXPORTS_DIR"]) / f"company_{company_id}" / name

    def _upload(self, data: bytes) -> str:
        response = self.client.post(
            "/admin/restore/upload",
            data={"backup_zip": (io.BytesIO(data), "backup.zip")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"]

    def _wait_for_jobs(self) -> None:
        deadline = time.time() + 30
        while any(j["status"] == "running" for j in _dexter._EXPORT_JOBS.values()):
            self.assertLess(time.time(), deadline)
            time.sleep(0.05)

    def test_restore_round_trip_only_touches_selected_company(self) -> None:
        self._login(self.super_admin, "Super Admin", self.alpha)
        backup = self._export_path(self.alpha).read_bytes()

        (self.storage / f"company_{self.alpha}" / "profile" / "alpha.txt").unlink()
        (self.ic3 / "inventory_database.json").write_text(
            json.dumps({"Alice": {"2026-01-01": {"P1": 0}, "2026-02-01": {"P1": 7}}, "Kingsville": {"2026-01-01": {"P1": 99}}})
        )
        pm = sqlite3.connect(self.pm_db)
        pm.execute("DELETE FROM product_mix_uploads")
        pm.commit()
        pm.close()

        location = self._upload(backup)
        self.assertTrue(location.startswith("/admin/restore/"), location)
        token = location.rsplit("/", 1)[1]
        preview = self.client.get(location)
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Restore Preview", preview.get_data(as_text=True))

        wrong = self.client.post(f"/admin/restore/{token}/apply", data={"confirm_slug": "beta-co"})
        self.assertIn("error=", wrong.headers["Location"])
        self.client.post(f"/admin/restore/{token}/apply", data={"confirm_slug": "alpha-co"})
        self._wait_for_jobs()
        job = [j for j in _dexter._EXPORT_JOBS.values() if j["kind"] == "restore"][-1]
        self.assertEqual(job["status"], "done", job.get("error"))

        self.assertEqual((self.storage / f"company_{self.alpha}" / "profile" / "alpha.txt").read_text(), "alpha")
        inventory = json.loads((self.ic3 / "inventory_database.json").read_text())
        self.assertEqual(inventory["Alice"]["2026-01-01"], {"P1": 5})
        self.assertEqual(inventory["Alice"]["2026-02-01"], {"P1": 7})
        self.assertEqual(inventory["Kingsville"]["2026-01-01"], {"P1": 99})
        pm = sqlite3.connect(self.pm_db)
        rows = pm.execute("SELECT id, restaurant_id FROM product_mix_uploads ORDER BY id").fetchall()
        pm.close()
        self.assertEqual(rows, [(10, 1)])

    def test_legacy_files_assigned_to_one_company_only(self) -> None:
        self._login(self.super_admin, "Super Admin", self.alpha)
        page = self.client.get("/admin/legacy-files")
        self.assertEqual(page.status_code, 200)
        self.assertIn("2025-11-07_Day.csv", page.get_data(as_text=True))

        self.client.post(
            "/admin/legacy-files/assign",
            data={"files": ["daily_logs|2025-11-07_Day.csv", "daily_logs|../../escape.txt", "nope|x"]},
        )
        copy = self.storage / f"company_{self.alpha}" / "legacy" / "daily_logs" / "2025-11-07_Day.csv"
        self.assertEqual(copy.read_text(), "day")

        self._login(self.super_admin, "Super Admin", self.beta)
        self.client.post("/admin/legacy-files/assign", data={"files": ["daily_logs|2025-11-07_Day.csv"]})
        self.assertFalse((self.storage / f"company_{self.beta}" / "legacy" / "daily_logs" / "2025-11-07_Day.csv").exists())
        denied = self.client.post("/admin/legacy-files/unassign", data={"file": "daily_logs|2025-11-07_Day.csv"})
        self.assertIn("error=", denied.headers["Location"])
        self.assertTrue(copy.exists())

        self._login(self.super_admin, "Super Admin", self.alpha)
        with zipfile.ZipFile(self._export_path(self.alpha)) as zf:
            self.assertIn("files/dexter/legacy/daily_logs/2025-11-07_Day.csv", zf.namelist())
        self.client.post("/admin/legacy-files/unassign", data={"file": "daily_logs|2025-11-07_Day.csv"})
        self.assertFalse(copy.exists())

    def test_restore_rejects_tampered_unsafe_and_foreign_backups(self) -> None:
        self._login(self.super_admin, "Super Admin", self.alpha)
        good = self._export_path(self.alpha).read_bytes()

        tampered = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(tampered, "w") as dst:
            for item in src.infolist():
                data = src.read(item)
                dst.writestr(item, b"changed" if item.filename.endswith("alpha.txt") else data)
        self.assertIn("Checksum", self._upload(tampered.getvalue()))

        unsafe = io.BytesIO()
        with zipfile.ZipFile(unsafe, "w") as zf:
            zf.writestr("../evil.txt", "x")
        self.assertIn("Unsafe", self._upload(unsafe.getvalue()))

        self._login(self.super_admin, "Super Admin", self.beta)
        beta_backup = self._export_path(self.beta).read_bytes()
        self._login(self.super_admin, "Super Admin", self.alpha)
        self.assertIn("belongs", self._upload(beta_backup))

    def test_manager_cannot_restore(self) -> None:
        self._login(self.manager, "Manager", self.alpha)
        self.assertEqual(self.client.get("/admin/legacy-files").status_code, 403)
        self.assertEqual(self.client.post("/admin/legacy-files/assign").status_code, 403)
        self.assertEqual(self.client.post("/admin/restore/upload").status_code, 403)
        self.assertEqual(self.client.post(f"/admin/restore/{'a' * 32}/apply").status_code, 403)


class CompanyPurgeSafetyTests(unittest.TestCase):
    def test_company_purge_is_disabled_without_explicit_opt_in(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEXTER_COMPANY_PURGE_ENABLED", None)
            with patch.object(_dexter, "_COMPANY_PURGE_THREAD_STARTED", False):
                with patch.object(_dexter.threading, "Thread") as thread_factory:
                    _dexter._start_company_purge_scheduler()

        thread_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
