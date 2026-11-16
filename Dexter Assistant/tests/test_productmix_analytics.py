import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("Requested functions were not found")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class ProductMixAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "analytics.db"
        self.namespace = load_functions(
            ROOT / "ProductMixRestaurantDB" / "app.py",
            [
                "_product_mix_analytics_uses_all_levels",
                "_get_product_mix_period_trend_rows",
                "_get_product_mix_item_totals_rows",
                "_get_product_mix_category_totals_rows",
            ],
            {
                "get_db_connection": self.connect,
                "_clean_text": lambda value, max_len: " ".join((value or "").split())[:max_len],
            },
        )
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE product_mix_uploads (
                    id INTEGER PRIMARY KEY,
                    restaurant_id INTEGER,
                    report_start_date TEXT,
                    report_end_date TEXT
                );
                CREATE TABLE product_mix_items (
                    id INTEGER PRIMARY KEY,
                    upload_id INTEGER,
                    restaurant_id INTEGER,
                    category_name TEXT,
                    item_name TEXT,
                    qty_sold REAL,
                    total REAL,
                    report_start_date TEXT,
                    report_end_date TEXT
                );
                CREATE TABLE all_levels_items (
                    id INTEGER PRIMARY KEY,
                    restaurant_id INTEGER,
                    item_name TEXT
                );
                CREATE TABLE all_levels_records (
                    id INTEGER PRIMARY KEY,
                    item_id INTEGER,
                    upload_id INTEGER,
                    restaurant_id INTEGER,
                    report_start_date TEXT,
                    report_end_date TEXT,
                    col_c TEXT,
                    col_i REAL
                );
                """
            )

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def add_legacy_record(self, item_id, upload_id, restaurant_id, item_name, category, day, quantity):
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO all_levels_items (id, restaurant_id, item_name) VALUES (?, ?, ?)",
                (item_id, restaurant_id, item_name),
            )
            conn.execute(
                """
                INSERT INTO all_levels_records
                (item_id, upload_id, restaurant_id, report_start_date, report_end_date, col_c, col_i)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, upload_id, restaurant_id, day, day, category, quantity),
            )

    def test_legacy_tracked_items_populate_analytics_and_respect_filters(self):
        self.add_legacy_record(1, 11, 1, "Burger", "Entrees", "2026-09-01", 2)
        self.add_legacy_record(2, 11, 1, "Fries", "Sides", "2026-09-01", 4)
        self.add_legacy_record(1, 12, 1, "Burger", "Entrees", "2026-09-02", 3)
        self.add_legacy_record(3, 13, 1, "Unassigned Item", "0.0", "2026-09-02", 2)
        self.add_legacy_record(4, 21, 2, "Other Burger", "Entrees", "2026-09-02", 99)

        restaurant = {"id": 1}
        period_rows = self.namespace["_get_product_mix_period_trend_rows"](restaurant)
        item_rows = self.namespace["_get_product_mix_item_totals_rows"](restaurant, limit=None)
        category_rows = self.namespace["_get_product_mix_category_totals_rows"](restaurant)

        self.assertEqual(len(period_rows), 1)
        self.assertEqual(period_rows[0]["period"], "2026-09")
        self.assertEqual(period_rows[0]["uploads"], 3)
        self.assertEqual(period_rows[0]["total_qty_sold"], 11)
        self.assertEqual(item_rows[0]["item_name"], "Burger")
        self.assertEqual(item_rows[0]["category_name"], "Entrees")
        self.assertEqual(item_rows[0]["total_units"], 5)
        self.assertEqual(
            {row["category_name"]: row["total_qty_sold"] for row in category_rows},
            {"Entrees": 5, "Sides": 4, "Uncategorized": 2},
        )

        filtered_rows = self.namespace["_get_product_mix_item_totals_rows"](
            restaurant,
            start_date="2026-09-02",
            end_date="2026-09-02",
            search_text="Entrees",
            limit=None,
        )
        self.assertEqual(len(filtered_rows), 1)
        self.assertEqual(filtered_rows[0]["item_name"], "Burger")
        self.assertEqual(filtered_rows[0]["total_qty_sold"], 3)

    def test_normalized_product_mix_data_remains_preferred(self):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO product_mix_uploads VALUES (31, 1, '2026-09-01', '2026-09-01')"
            )
            conn.execute(
                """
                INSERT INTO product_mix_items
                VALUES (1, 31, 1, 'Entrees', 'Normalized Burger', 2, 6, '2026-09-01', '2026-09-01')
                """
            )
        self.add_legacy_record(1, 41, 1, "Legacy Burger", "Entrees", "2026-09-01", 99)

        rows = self.namespace["_get_product_mix_item_totals_rows"]({"id": 1}, limit=None)

        self.assertEqual([row["item_name"] for row in rows], ["Normalized Burger"])
        self.assertEqual(rows[0]["total_units"], 6)


if __name__ == "__main__":
    unittest.main()
