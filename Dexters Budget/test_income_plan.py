import sqlite3
import unittest

import app as budget_app


class IncomePlanBudgetTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(budget_app.SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_income_plan_uses_latest_recurring_and_mortgage_budget(self):
        self.conn.executemany(
            """
            INSERT INTO transactions (date, amount, description, merchant, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("2026-01-10", -10.00, "Old subscription", "STREAMING", "recurring"),
                ("2026-02-10", -12.00, "Current subscription", "STREAMING", "recurring"),
                ("2026-01-02", -1000.00, "Mortgage", "ROCKET", "mortgage"),
            ],
        )
        self.conn.execute(
            """
            INSERT INTO manual_entries (date, amount, merchant, category, entry_type, notes)
            VALUES ('2026-03-01', -50.00, 'UTILITY', 'recurring', 'expense', 'Monthly utility')
            """
        )

        result = budget_app.compute_income_plan(
            {
                "income_1": 2000,
                "income_2": 1000,
                "current_balance_1": 100,
                "current_balance_2": 50,
                "run_month": "2026-07",
            },
            self.conn,
        )

        self.assertEqual(result["monthly_expenses"]["recurring"], 62.00)
        self.assertEqual(result["monthly_expenses"]["mortgage"], 1000.00)
        self.assertEqual(result["monthly_expenses"]["expense"], 0.00)
        self.assertEqual(result["monthly_expenses"]["total"], 1062.00)
        self.assertEqual(result["adjusted_bills_split"]["amount_due_after_balance"], 912.00)
        self.assertEqual(result["inputs"]["budget_basis"], "latest_recurring_and_mortgage")


if __name__ == "__main__":
    unittest.main()