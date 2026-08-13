from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._dexter_test_harness import load_dexter_module

_mod = load_dexter_module()
_app = _mod.app
_rate_limit_key = _mod._rate_limit_key


def _call_key(headers: dict[str, str], remote_addr: str = "1.2.3.4") -> str:
    with _app.test_request_context(
        "/login",
        headers=headers,
        environ_base={"REMOTE_ADDR": remote_addr},
    ):
        return _rate_limit_key()


class TestRateLimitKeyUsesRemoteAddressOnly(unittest.TestCase):
    def test_no_headers_returns_remote_addr(self):
        self.assertEqual(_call_key({}), "1.2.3.4")

    def test_spoofed_x_forwarded_for_is_ignored(self):
        result = _call_key({"X-Forwarded-For": "10.0.0.1"}, remote_addr="1.2.3.4")
        self.assertEqual(result, "1.2.3.4")
        self.assertNotIn("10.0.0.1", result)

    def test_spoofed_x_forwarded_for_chain_is_ignored(self):
        result = _call_key({"X-Forwarded-For": "10.0.0.1, 172.16.0.5"}, remote_addr="1.2.3.4")
        self.assertEqual(result, "1.2.3.4")

    def test_spoofed_x_dexter_user_is_ignored(self):
        result = _call_key({"X-Dexter-User": "admin"}, remote_addr="1.2.3.4")
        self.assertEqual(result, "1.2.3.4")
        self.assertNotIn("admin", result)

    def test_both_spoofed_headers_ignored(self):
        result = _call_key(
            {"X-Forwarded-For": "5.5.5.5", "X-Dexter-User": "superuser"},
            remote_addr="1.2.3.4",
        )
        self.assertEqual(result, "1.2.3.4")

    def test_different_clients_produce_different_keys(self):
        key_a = _call_key({}, remote_addr="9.9.9.1")
        key_b = _call_key({}, remote_addr="9.9.9.2")
        self.assertNotEqual(key_a, key_b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
