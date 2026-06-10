from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

DEXTER_ROOT = Path(__file__).resolve().parents[1]
if str(DEXTER_ROOT) not in sys.path:
    sys.path.insert(0, str(DEXTER_ROOT))

from tenant_scope import resolve_tenant_scope, tenant_blank_state_required


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class TenantScopeMatrixTests(unittest.TestCase):
    def test_header_company_wins_over_session_company(self) -> None:
        scope = resolve_tenant_scope(
            {
                "X-Dexter-Auth": "1",
                "X-Dexter-Company-Name": "Event Mania",
                "X-Dexter-Restaurant-Name": "No Restaurant",
            },
            session_data={"pm_selected_company": "Big House Burgers"},
            company_session_keys=("pm_selected_company",),
        )

        self.assertTrue(scope["is_dexter_proxy"])
        self.assertEqual(scope["company_name"], "Event Mania")
        self.assertEqual(scope["restaurant_name"], "No Restaurant")

    def test_session_company_is_used_when_header_missing(self) -> None:
        scope = resolve_tenant_scope(
            {},
            session_data={"pm_selected_company": "Big House Burgers"},
            company_session_keys=("pm_selected_company",),
        )

        self.assertFalse(scope["is_dexter_proxy"])
        self.assertEqual(scope["company_name"], "Big House Burgers")

    def test_logs_missing_scope_once_per_route(self) -> None:
        logger = logging.getLogger("tenant-scope-test")
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        handler = _ListHandler()
        logger.addHandler(handler)
        try:
            for _ in range(2):
                resolve_tenant_scope(
                    {"X-Dexter-Auth": "1"},
                    app_name="ic3",
                    logger=logger,
                    request_path="/api/dexter/context",
                    method="GET",
                )
        finally:
            logger.removeHandler(handler)

        self.assertEqual(len(handler.messages), 1)
        self.assertIn("missing tenant company scope", handler.messages[0])

    def test_blank_state_matrix_three_companies(self) -> None:
        company_locations = {
            "Big House Burgers": ["Kingsville", "Alice"],
            "Event Mania": [],
            "Future Foods": ["Downtown"],
        }

        for company_name, locations in company_locations.items():
            is_blank = tenant_blank_state_required(company_name, len(locations))
            if company_name == "Event Mania":
                self.assertTrue(is_blank)
            else:
                self.assertFalse(is_blank)


if __name__ == "__main__":
    unittest.main(verbosity=2)
