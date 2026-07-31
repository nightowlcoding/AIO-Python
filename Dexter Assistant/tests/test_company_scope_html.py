from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from _dexter_test_harness import load_dexter_module


_dexter = load_dexter_module()


class CompanyScopeHtmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        _dexter.RBAC_DB_PATH = _dexter.Path(self.tmp.name) / "rbac_test.db"

        _dexter.app.config["TESTING"] = True
        _dexter.app.config["WTF_CSRF_ENABLED"] = False

        _dexter.initialize_rbac_db()
        _dexter.migrate_add_task_fields_v1()
        _dexter.migrate_add_password_reset_fields_v1()
        _dexter.migrate_add_company_scope_v1()

        self.ids = self._seed_rbac_data()
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
                    (
                        "mgr_alpha",
                        _dexter.generate_password_hash("manager-password-123"),
                        role_ids["Manager"],
                        alpha_id,
                    ),
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
            employee_beta_id = int(
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, company_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    ("emp_beta", "hash", role_ids["Employee"], beta_id),
                ).lastrowid
            )

            conn.commit()
            return {
                "alpha_company_id": alpha_id,
                "beta_company_id": beta_id,
                "gamma_inactive_company_id": gamma_inactive_id,
                "super_admin_id": super_admin_id,
                "manager_id": manager_id,
                "lockout_user_id": lockout_user_id,
                "employee_beta_id": employee_beta_id,
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
    ) -> None:
        with self.client.session_transaction() as sess:
            sess[_dexter.SESSION_USER_KEY] = {
                "username": f"user_{user_id}",
                "user_id": int(user_id),
                "role_name": role_name,
                "company_id": int(company_id) if company_id is not None else None,
                "selected_company_id": int(selected_company_id) if selected_company_id is not None else None,
                "company_name": "Test Company",
                "is_admin": role_name == "Super Admin",
                "email": f"user_{user_id}@example.com",
            }

    def _redirect_error(self, response) -> str:
        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertTrue(location.startswith("/admin/"))
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        return params.get("error", [""])[0]

    def test_html_users_create_requires_super_admin_selected_scope(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=None,
        )

        res = self.client.post(
            "/admin/users/create",
            data={"username": "html_new_1", "password": "password123", "role_name": "Employee"},
            follow_redirects=False,
        )

        self.assertIn("No active company scope is selected", self._redirect_error(res))

    def test_html_tasks_create_rejects_inactive_super_admin_scope(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["gamma_inactive_company_id"],
        )

        res = self.client.post(
            "/admin/tasks/create",
            data={"title": "Task blocked", "description": "blocked", "priority": "normal"},
            follow_redirects=False,
        )

        self.assertIn("Selected company is not active or does not exist", self._redirect_error(res))

    def test_html_user_role_change_blocks_cross_company_for_super_admin(self) -> None:
        self._set_session_user(
            user_id=self.ids["super_admin_id"],
            role_name="Super Admin",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["alpha_company_id"],
        )

        res = self.client.post(
            f"/admin/users/{self.ids['employee_beta_id']}/role",
            data={"role_name": "Manager"},
            follow_redirects=False,
        )

        self.assertIn("Forbidden: user is outside selected company scope", self._redirect_error(res))

    def test_html_users_create_manager_stays_with_manager_company(self) -> None:
        self._set_session_user(
            user_id=self.ids["manager_id"],
            role_name="Manager",
            company_id=self.ids["alpha_company_id"],
            selected_company_id=self.ids["beta_company_id"],
        )

        res = self.client.post(
            "/admin/users/create",
            data={"username": "mgr_html_new", "password": "password123", "role_name": "Employee"},
            follow_redirects=False,
        )

        self.assertEqual(res.status_code, 302)
        location = res.headers.get("Location", "")
        self.assertIn("/admin/users?message=", location)

        conn = _dexter.get_rbac_db_connection()
        try:
            row = conn.execute(
                "SELECT company_id FROM users WHERE username = ? LIMIT 1",
                ("mgr_html_new",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["company_id"]), self.ids["alpha_company_id"])
        finally:
            conn.close()

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

    def test_manager_login_redirects_without_starting_all_apps(self) -> None:
        with patch.object(_dexter.MANAGER, "start_all") as start_all:
            response = self.client.post(
                "/auth/login",
                data={"username": "mgr_alpha", "password": "manager-password-123"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), "/portal/managerapp")
        start_all.assert_not_called()
        with self.client.session_transaction() as sess:
            self.assertEqual(sess[_dexter.SESSION_USER_KEY]["role_name"], "Manager")

    def test_security_headers_present_on_login_page(self) -> None:
        res = self.client.get("/auth/login")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertEqual(res.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")
        csp = res.headers.get("Content-Security-Policy", "")
        self.assertIn("frame-ancestors 'self'", csp)

    def test_cookie_security_defaults_are_hardened(self) -> None:
        self.assertTrue(bool(_dexter.app.config.get("SESSION_COOKIE_HTTPONLY")))
        self.assertEqual(str(_dexter.app.config.get("SESSION_COOKIE_SAMESITE")), "Lax")
        self.assertEqual(str(_dexter.app.config.get("SESSION_COOKIE_NAME")), "dexter_session")


if __name__ == "__main__":
    unittest.main(verbosity=2)
