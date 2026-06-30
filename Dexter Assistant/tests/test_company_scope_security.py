from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from _dexter_test_harness import load_dexter_module


_dexter = load_dexter_module()


class CompanyScopeSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        _dexter.RBAC_DB_PATH = _dexter.Path(self.tmp.name) / "rbac_test.db"
        _dexter.ROOT = _dexter.Path(self.tmp.name)
        _dexter.COMPANY_STORAGE_ROOT = _dexter.Path(self.tmp.name) / "company_data"
        _dexter.app.config["TESTING"] = True
        _dexter.app.config["WTF_CSRF_ENABLED"] = False

        _dexter.initialize_rbac_db()
        _dexter.migrate_add_task_fields_v1()
        _dexter.migrate_add_password_reset_fields_v1()
        _dexter.migrate_add_company_scope_v1()
        _dexter.migrate_add_user_location_assignments_v1()

        self.ids = self._seed_rbac_data()
        self._seed_company_storage()
        self._seed_productmix_restaurants()
        self.client = _dexter.app.test_client()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_rbac_data(self) -> dict[str, int]:
        conn = _dexter.get_rbac_db_connection()
        try:
            role_ids = {
                row["name"]: int(row["id"])
                for row in conn.execute("SELECT id, name FROM roles").fetchall()
            }

            alpha_id = int(
                conn.execute(
                    "INSERT INTO companies (name, slug, is_active) VALUES ('Alpha Co', 'alpha-co', 1)"
                ).lastrowid
            )
            beta_id = int(
                conn.execute(
                    "INSERT INTO companies (name, slug, is_active) VALUES ('Beta Co', 'beta-co', 1)"
                ).lastrowid
            )
            gamma_inactive_id = int(
                conn.execute(
                    "INSERT INTO companies (name, slug, is_active) VALUES ('Gamma Co', 'gamma-co', 0)"
                ).lastrowid
            )

            super_admin_id = int(
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, company_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    ("sa_alpha", "hash", role_ids["Super Admin"], alpha_id),
                ).lastrowid
            )
            manager_id = int(
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, company_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    ("mgr_alpha", "hash", role_ids["Manager"], alpha_id),
                ).lastrowid
            )
            employee_beta_id = int(
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, company_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    ("emp_beta", "hash", role_ids["Employee"], beta_id),
                ).lastrowid
            )
            lockout_user_id = int(
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, company_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (
                        "lock_user",
                        _dexter.generate_password_hash("correct-password-123"),
                        role_ids["Employee"],
                        alpha_id,
                    ),
                ).lastrowid
            )

            alpha_task_id = int(
                conn.execute(
                    """
                    INSERT INTO tasks (title, description, status, created_by, assigned_to, company_id)
                    VALUES (?, ?, 'pending', ?, ?, ?)
                    """,
                    ("Alpha Task", "local check", super_admin_id, manager_id, alpha_id),
                ).lastrowid
            )
            task_beta_id = int(
                conn.execute(
                    """
                    INSERT INTO tasks (title, description, status, created_by, assigned_to, company_id)
                    VALUES (?, ?, 'pending', ?, ?, ?)
                    """,
                    ("Beta Task", "cross-company check", employee_beta_id, employee_beta_id, beta_id),
                ).lastrowid
            )

            conn.commit()
            return {
                "alpha_company_id": alpha_id,
                "beta_company_id": beta_id,
                "gamma_inactive_company_id": gamma_inactive_id,
                "super_admin_id": super_admin_id,
                "manager_id": manager_id,
                "employee_beta_id": employee_beta_id,
                "lockout_user_id": lockout_user_id,
                "alpha_task_id": alpha_task_id,
                "task_beta_id": task_beta_id,
            }
        finally:
            conn.close()

    def _set_session_user(
        self,
        *,
        user_id: int,
        role_name: str,
        company_id: int | None,
        selected_company_id: int | None,
        selected_restaurant_id: int | None = None,
    ) -> None:
        with self.client.session_transaction() as sess:
            sess[_dexter.SESSION_USER_KEY] = {
                "username": f"user_{user_id}",
                "user_id": int(user_id),
                "role_name": role_name,
                "company_id": int(company_id) if company_id is not None else None,
                "selected_company_id": int(selected_company_id) if selected_company_id is not None else None,
                "selected_restaurant_id": int(selected_restaurant_id) if selected_restaurant_id is not None else None,
                "company_name": "Test Company",
                "is_admin": role_name == "Super Admin",
                "email": f"user_{user_id}@example.com",
            }

    def _seed_company_storage(self) -> None:
        alpha_file = _dexter._resolve_company_storage_path(self.ids["alpha_company_id"], "reports/alpha.txt", create_parent=True)
        beta_file = _dexter._resolve_company_storage_path(self.ids["beta_company_id"], "reports/beta.txt", create_parent=True)
        assert alpha_file is not None
        assert beta_file is not None
        alpha_file.write_text("alpha report", encoding="utf-8")
        beta_file.write_text("beta report", encoding="utf-8")

    def _seed_productmix_restaurants(self) -> None:
        productmix_dir = _dexter.ROOT / "ProductMixRestaurantDB"
        productmix_dir.mkdir(parents=True, exist_ok=True)
        pm_db_path = productmix_dir / "product_mix.db"
        conn = sqlite3.connect(pm_db_path)
        try:
            conn.execute(
                """
                CREATE TABLE restaurants (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    location TEXT,
                    city TEXT,
                    state TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO restaurants (id, name, location, city, state) VALUES (?, ?, ?, ?, ?)",
                [
                    (101, "Alpha Co", "Alice", "Alice", "TX"),
                    (102, "Alpha Co", "Kingsville", "Kingsville", "TX"),
                    (201, "Beta Co", "Downtown", "Houston", "TX"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def test_super_admin_create_user_requires_selected_scope(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=None,
        )

        res = self.client.post(
            "/api/admin/users",
            json={"username": "new_no_scope", "password": "password123", "role_name": "Employee"},
        )

        self.assertEqual(res.status_code, 403)
        self.assertIn("No active company scope is selected", (res.get_json() or {}).get("message", ""))

    def test_super_admin_create_user_rejects_inactive_selected_scope(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["gamma_inactive_company_id"],
        )

        res = self.client.post(
            "/api/admin/users",
            json={"username": "new_inactive_scope", "password": "password123", "role_name": "Employee"},
        )

        self.assertEqual(res.status_code, 403)
        self.assertIn("Selected company is not active or does not exist", (res.get_json() or {}).get("message", ""))

    def test_super_admin_create_user_uses_selected_scope(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.post(
            "/api/admin/users",
            json={"username": "new_alpha_user", "password": "password123", "role_name": "Employee"},
        )

        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))

        conn = _dexter.get_rbac_db_connection()
        try:
            row = conn.execute(
                "SELECT company_id FROM users WHERE username = ? LIMIT 1",
                ("new_alpha_user",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["company_id"]), self.ids["alpha_company_id"])
        finally:
            conn.close()

    def test_super_admin_create_user_saves_location_assignments(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.post(
            "/api/admin/users",
            json={
                "username": "alice_only_mgr",
                "password": "password123",
                "role_name": "Manager",
                "restaurant_ids": [101],
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))

        conn = _dexter.get_rbac_db_connection()
        try:
            user_row = conn.execute("SELECT id FROM users WHERE username = ? LIMIT 1", ("alice_only_mgr",)).fetchone()
            self.assertIsNotNone(user_row)
            assignment_rows = conn.execute(
                "SELECT restaurant_id FROM user_location_assignments WHERE user_id = ? ORDER BY restaurant_id ASC",
                (int(user_row["id"]),),
            ).fetchall()
            self.assertEqual([int(row["restaurant_id"]) for row in assignment_rows], [101])
        finally:
            conn.close()

    def test_shared_restaurants_filters_to_manager_assigned_locations(self) -> None:
        conn = _dexter.get_rbac_db_connection()
        try:
            conn.execute(
                "INSERT INTO user_location_assignments (user_id, company_id, restaurant_id) VALUES (?, ?, ?)",
                (self.ids["manager_id"], self.ids["alpha_company_id"], 101),
            )
            conn.commit()
        finally:
            conn.close()

        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.get("/api/shared/restaurants")

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual([int(item["id"]) for item in payload.get("restaurants", [])], [101])

    def test_shared_restaurants_respects_selected_location(self) -> None:
        conn = _dexter.get_rbac_db_connection()
        try:
            conn.executemany(
                "INSERT INTO user_location_assignments (user_id, company_id, restaurant_id) VALUES (?, ?, ?)",
                [
                    (self.ids["manager_id"], self.ids["alpha_company_id"], 101),
                    (self.ids["manager_id"], self.ids["alpha_company_id"], 102),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
            selected_restaurant_id=102,
        )

        res = self.client.get("/api/shared/restaurants")

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual([int(item["id"]) for item in payload.get("restaurants", [])], [102])

    def test_api_location_scope_switch_updates_selected_restaurant(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.patch(
            "/api/admin/location-scope",
            json={"restaurant_id": 102},
        )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual(int((payload.get("restaurant") or {}).get("id") or 0), 102)

        with self.client.session_transaction() as sess:
            user = sess.get(_dexter.SESSION_USER_KEY) or {}
            self.assertEqual(int(user.get("selected_restaurant_id") or 0), 102)

    def test_api_location_scope_switch_rejects_out_of_company_location(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.patch(
            "/api/admin/location-scope",
            json={"restaurant_id": 201},
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid location selection", (res.get_json() or {}).get("message", ""))

    def test_api_company_scope_switch_rebinds_selected_location_to_target_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
            selected_restaurant_id=101,
        )

        res = self.client.patch(
            "/api/admin/company-scope",
            json={"company_id": self.ids["beta_company_id"]},
        )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual(int((payload.get("company") or {}).get("id") or 0), self.ids["beta_company_id"])

        with self.client.session_transaction() as sess:
            user = sess.get(_dexter.SESSION_USER_KEY) or {}
            self.assertEqual(int(user.get("selected_company_id") or 0), self.ids["beta_company_id"])
            self.assertEqual(int(user.get("selected_restaurant_id") or 0), 201)

        shared_res = self.client.get("/api/shared/restaurants")
        self.assertEqual(shared_res.status_code, 200)
        shared_payload = shared_res.get_json() or {}
        self.assertTrue(shared_payload.get("ok"))
        self.assertEqual([int(item["id"]) for item in shared_payload.get("restaurants", [])], [201])

    def test_api_company_scope_switch_with_no_locations_clears_selected_location(self) -> None:
        conn = _dexter.get_rbac_db_connection()
        try:
            empty_company_id = int(
                conn.execute(
                    "INSERT INTO companies (name, slug, is_active) VALUES ('No Locations Co', 'no-locations-co', 1)"
                ).lastrowid
            )
            conn.commit()
        finally:
            conn.close()

        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
            selected_restaurant_id=101,
        )

        res = self.client.patch(
            "/api/admin/company-scope",
            json={"company_id": empty_company_id},
        )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))

        with self.client.session_transaction() as sess:
            user = sess.get(_dexter.SESSION_USER_KEY) or {}
            self.assertEqual(int(user.get("selected_company_id") or 0), int(empty_company_id))
            self.assertIsNone(user.get("selected_restaurant_id"))

        shared_res = self.client.get("/api/shared/restaurants")
        self.assertEqual(shared_res.status_code, 200)
        shared_payload = shared_res.get_json() or {}
        self.assertTrue(shared_payload.get("ok"))
        self.assertEqual(shared_payload.get("restaurants", []), [])

    def test_tenant_scope_audit_endpoint_reports_monitored_routes_ok(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.get("/api/admin/tenant-scope-audit")

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        checks = payload.get("checks") or []
        self.assertTrue(checks)

        checks_by_endpoint = {str(item.get("endpoint")): item for item in checks if isinstance(item, dict)}
        self.assertIn("api_shared_restaurants", checks_by_endpoint)
        self.assertIn("api_admin_company_scope_switch", checks_by_endpoint)
        self.assertIn("api_admin_location_scope_switch", checks_by_endpoint)
        self.assertTrue(bool(checks_by_endpoint["api_shared_restaurants"].get("ok")))
        self.assertTrue(bool(checks_by_endpoint["api_admin_company_scope_switch"].get("ok")))
        self.assertTrue(bool(checks_by_endpoint["api_admin_location_scope_switch"].get("ok")))

    def test_super_admin_role_change_blocked_cross_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.patch(
            f"/api/admin/users/{self.ids['employee_beta_id']}/role",
            json={"role_name": "Manager"},
        )

        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden: user is outside selected company scope", (res.get_json() or {}).get("message", ""))

    def test_super_admin_task_status_blocked_cross_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.patch(
            f"/api/admin/tasks/{self.ids['task_beta_id']}/status",
            json={"status": "completed"},
        )

        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden: task is outside selected company scope", (res.get_json() or {}).get("message", ""))

    def test_manager_create_user_forces_manager_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.post(
            "/api/admin/users",
            json={"username": "new_mgr_created", "password": "password123", "role_name": "Employee"},
        )

        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))

        conn = _dexter.get_rbac_db_connection()
        try:
            row = conn.execute(
                "SELECT company_id FROM users WHERE username = ? LIMIT 1",
                ("new_mgr_created",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["company_id"]), self.ids["alpha_company_id"])
        finally:
            conn.close()

    def test_audit_details_are_redacted_for_manager_but_full_for_super_admin(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        created = self.client.post(
            "/api/admin/users",
            json={"username": "audit_redact_user", "password": "password123", "role_name": "Employee"},
        )
        self.assertEqual(created.status_code, 200)

        manager_logs = self.client.get("/api/admin/audit-logs")
        self.assertEqual(manager_logs.status_code, 200)
        manager_payload = manager_logs.get_json() or {}
        manager_create_log = next(
            row for row in manager_payload.get("audit_logs", [])
            if row.get("action") == "create_user" and row.get("target_table") == "users"
        )
        manager_details = str(manager_create_log.get("details", ""))
        self.assertIn("[REDACTED]", manager_details)
        self.assertNotIn("audit_redact_user", manager_details)

        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )
        super_logs = self.client.get("/api/admin/audit-logs")
        self.assertEqual(super_logs.status_code, 200)
        super_payload = super_logs.get_json() or {}
        super_create_log = next(
            row for row in super_payload.get("audit_logs", [])
            if row.get("action") == "create_user" and row.get("target_table") == "users"
        )
        self.assertIn("audit_redact_user", str(super_create_log.get("details", "")))

    def test_super_admin_reads_are_scoped_to_selected_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        users_res = self.client.get("/api/admin/users")
        tasks_res = self.client.get("/api/admin/tasks")

        self.assertEqual(users_res.status_code, 200)
        self.assertEqual(tasks_res.status_code, 200)

        users_payload = users_res.get_json() or {}
        tasks_payload = tasks_res.get_json() or {}
        user_names = {row["username"] for row in users_payload.get("users", [])}
        task_titles = {row["title"] for row in tasks_payload.get("tasks", [])}

        self.assertIn("sa_alpha", user_names)
        self.assertIn("mgr_alpha", user_names)
        self.assertNotIn("emp_beta", user_names)
        self.assertIn("Alpha Task", task_titles)
        self.assertNotIn("Beta Task", task_titles)

    def test_manager_tampered_selected_scope_is_ignored(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 200)

        payload = res.get_json() or {}
        user_names = {row["username"] for row in payload.get("users", [])}
        self.assertIn("sa_alpha", user_names)
        self.assertIn("mgr_alpha", user_names)
        self.assertNotIn("emp_beta", user_names)

    def test_login_lockout_after_repeated_failures(self) -> None:
        for _ in range(4):
            res = self.client.post(
                "/auth/login",
                data={"username": "lock_user", "password": "wrong-password"},
                follow_redirects=False,
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn("attempts remaining before temporary lockout", res.get_data(as_text=True))

        fifth = self.client.post(
            "/auth/login",
            data={"username": "lock_user", "password": "wrong-password"},
            follow_redirects=False,
        )
        self.assertEqual(fifth.status_code, 200)
        self.assertIn("Account temporarily locked", fifth.get_data(as_text=True))

        blocked = self.client.post(
            "/auth/login",
            data={"username": "lock_user", "password": "correct-password-123"},
            follow_redirects=False,
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertIn("Account temporarily locked", blocked.get_data(as_text=True))

    def test_company_storage_is_scoped_by_selected_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.get("/api/admin/company-files?path=reports")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        entry_names = {entry["name"] for entry in payload.get("entries", [])}
        self.assertIn("alpha.txt", entry_names)
        self.assertNotIn("beta.txt", entry_names)

    def test_company_storage_traversal_is_blocked(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.get("/api/admin/company-files/download?path=../company_2/reports/beta.txt")
        self.assertIn(res.status_code, {403, 404})
        if res.status_code == 403:
            self.assertIn("Forbidden path", (res.get_json() or {}).get("message", ""))

    def test_company_storage_download_stays_with_manager_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.get("/api/admin/company-files/download?path=reports/alpha.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"alpha report", res.data)

    def test_company_storage_resolver_rejects_absolute_paths(self) -> None:
        self.assertIsNone(_dexter._resolve_company_storage_path(self.ids["alpha_company_id"], str(self.tmp.name)))

    def test_company_storage_resolver_blocks_traversal(self) -> None:
        sibling_path = f"../company_{self.ids['beta_company_id']}/reports/beta.txt"
        self.assertIsNone(_dexter._resolve_company_storage_path(self.ids["alpha_company_id"], sibling_path))

    def test_branding_company_logo_tracks_selected_company_scope(self) -> None:
        alpha_logo = _dexter._resolve_company_storage_path(self.ids["alpha_company_id"], "profile/logo.png", create_parent=True)
        beta_logo = _dexter._resolve_company_storage_path(self.ids["beta_company_id"], "profile/logo.png", create_parent=True)
        assert alpha_logo is not None
        assert beta_logo is not None
        alpha_logo.write_bytes(b"alpha-logo-bytes")
        beta_logo.write_bytes(b"beta-logo-bytes")

        _dexter.upsert_company_profile(self.ids["alpha_company_id"], {"logo_rel_path": "profile/logo.png"})
        _dexter.upsert_company_profile(self.ids["beta_company_id"], {"logo_rel_path": "profile/logo.png"})

        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        alpha_res = self.client.get("/branding/company-logo")
        self.assertEqual(alpha_res.status_code, 200)
        self.assertEqual(alpha_res.data, b"alpha-logo-bytes")

        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        beta_res = self.client.get("/branding/company-logo")
        self.assertEqual(beta_res.status_code, 200)
        self.assertEqual(beta_res.data, b"beta-logo-bytes")

    def test_branding_company_logo_is_not_cacheable(self) -> None:
        alpha_logo = _dexter._resolve_company_storage_path(self.ids["alpha_company_id"], "profile/logo.png", create_parent=True)
        assert alpha_logo is not None
        alpha_logo.write_bytes(b"alpha-logo-bytes")
        _dexter.upsert_company_profile(self.ids["alpha_company_id"], {"logo_rel_path": "profile/logo.png"})

        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.get("/branding/company-logo")
        self.assertEqual(res.status_code, 200)
        cache_control = str(res.headers.get("Cache-Control") or "")
        self.assertIn("no-store", cache_control)
        self.assertIn("private", cache_control)
        self.assertIn("no-cache", str(res.headers.get("Pragma") or ""))
        self.assertEqual(str(res.headers.get("Expires") or ""), "0")
        vary_value = str(res.headers.get("Vary") or "")
        self.assertIn("Cookie", vary_value)

    def test_manager_company_profile_update_stays_in_manager_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.post(
            "/admin/company-profile",
            data={
                "contact_email": "alpha-profile@example.com",
                "contact_phone": "555-0100",
                "notes": "alpha scoped note",
                "clear_logo": "0",
            },
            follow_redirects=False,
        )

        self.assertEqual(res.status_code, 302)

        conn = _dexter.get_rbac_db_connection()
        try:
            alpha = conn.execute(
                "SELECT contact_email, notes FROM company_profiles WHERE company_id = ? LIMIT 1",
                (self.ids["alpha_company_id"],),
            ).fetchone()
            beta = conn.execute(
                "SELECT contact_email, notes FROM company_profiles WHERE company_id = ? LIMIT 1",
                (self.ids["beta_company_id"],),
            ).fetchone()

            self.assertIsNotNone(alpha)
            self.assertEqual(str(alpha["contact_email"] or ""), "alpha-profile@example.com")
            self.assertEqual(str(alpha["notes"] or ""), "alpha scoped note")

            beta_email = "" if beta is None else str(beta["contact_email"] or "")
            beta_notes = "" if beta is None else str(beta["notes"] or "")
            self.assertNotEqual(beta_email, "alpha-profile@example.com")
            self.assertNotEqual(beta_notes, "alpha scoped note")
        finally:
            conn.close()

    def test_initialize_rbac_db_upgrades_legacy_schema(self) -> None:
        legacy_db = _dexter.Path(self.tmp.name) / "legacy_rbac.db"
        conn = sqlite3.connect(legacy_db)
        try:
            conn.executescript(
                """
                CREATE TABLE roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (role_id) REFERENCES roles(id)
                );

                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_by INTEGER NOT NULL,
                    assigned_to INTEGER,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    completed_at TEXT,
                    FOREIGN KEY (created_by) REFERENCES users(id),
                    FOREIGN KEY (assigned_to) REFERENCES users(id)
                );

                CREATE TABLE audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    target_id INTEGER,
                    details TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (actor_user_id) REFERENCES users(id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        original_db_path = _dexter.RBAC_DB_PATH
        try:
            _dexter.RBAC_DB_PATH = legacy_db
            _dexter.initialize_rbac_db()
            _dexter.migrate_add_company_scope_v1()

            conn = _dexter.get_rbac_db_connection()
            try:
                user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
                task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
                audit_columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
                self.assertIn("company_id", user_columns)
                self.assertIn("company_id", task_columns)
                self.assertIn("company_id", audit_columns)
            finally:
                conn.close()
        finally:
            _dexter.RBAC_DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main(verbosity=2)
