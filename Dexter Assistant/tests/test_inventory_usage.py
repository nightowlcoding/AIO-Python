import ast
import csv
import io
import json
import logging
import math
import re
import tempfile
import unittest
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request


ROOT = Path(__file__).resolve().parents[1]


class InventoryUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name) / "data"
        self.data_dir.mkdir()
        self.app = Flask(__name__)
        source = ROOT / "Inventory Control 3" / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        names = {
            "_canonical_product_number", "_safe_parse_date", "_usage_to_float",
            "_usage_measurement", "_usage_parse_bool", "_usage_iter_days",
            "_usage_group_by_product_inventory", "_usage_group_by_product_receipts",
            "_usage_prepare_inventory", "_usage_snapshot_value_prepared",
            "_usage_daily_series_for_product", "_usage_daily_summary",
            "_usage_velocity_profile", "_register_usage_reports_endpoints",
        }
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in functions}, names)
        self.ns = {
            "date": date, "datetime": datetime, "timedelta": timedelta,
            "defaultdict": defaultdict, "bisect_left": bisect_left, "bisect_right": bisect_right,
            "math": math, "re": re, "json": json, "csv": csv, "io": io, "logging": logging,
            "request": request, "jsonify": jsonify, "ROOT": Path(self.temp.name),
            "INVOICE_IMPORT_LOG_PATH": self.data_dir / "invoice_import_log.json",
            "_effective_runtime_location": lambda: "Alice",
            "products_list": [{"Product Number": "123", "Product Description": "Burger"}],
            "inventory_data": {}, "invoice_import_log": [],
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), self.ns)
        self.ns["_register_usage_reports_endpoints"](self.app)
        self.client = self.app.test_client()

    def save_data(self, inventory, invoices):
        (self.data_dir / "inventory_database.json").write_text(json.dumps(inventory), encoding="utf-8")
        (self.data_dir / "invoice_import_log.json").write_text(json.dumps(invoices), encoding="utf-8")

    def test_count_gap_conserves_usage_and_clipped_days_remain_estimates(self):
        counts = {"2026-01-01": 10, "2026-01-04": 7}
        receipts = {"2026-01-02": 3, "2026-01-04": 99}
        rows, weekdays = self.ns["_usage_daily_series_for_product"](
            counts, receipts, date(2026, 1, 1), date(2026, 1, 3),
        )
        self.assertEqual([row["usage"] for row in rows], [2, 2, 2])
        self.assertEqual(math.fsum(row["usage"] for row in rows), 10 + 3 - 7)
        self.assertTrue(all(row["calculation_mode"] == "estimated_gap" for row in rows))
        self.assertEqual(weekdays["thursday"], 2)
        self.assertIsNone(weekdays["monday"])
        for row in rows:
            self.assertAlmostEqual(row["usage"], row["opening_inventory"] + row["receipts"] - row["closing_inventory"])

        clipped, _ = self.ns["_usage_daily_series_for_product"](
            counts, receipts, date(2026, 1, 2), date(2026, 1, 4),
        )
        self.assertEqual([row["usage"] for row in clipped], [2, 2, None])
        self.assertEqual(clipped[-1]["calculation_mode"], "unavailable")

    def test_fractional_usage_is_not_rounded_before_averaging(self):
        rows, _ = self.ns["_usage_daily_series_for_product"](
            {"2026-01-01": 1, "2026-01-04": 0}, {},
            date(2026, 1, 1), date(2026, 1, 3),
        )
        summary = self.ns["_usage_daily_summary"](rows)
        self.assertAlmostEqual(summary["usage"], 1)
        self.assertAlmostEqual(summary["avg_daily_usage"], 1 / 3)

    def test_52_week_windows_do_not_overlap_or_extend_the_requested_range(self):
        start = date(2026, 1, 4)
        end = start + timedelta(days=363)
        self.ns["inventory_data"] = {"Alice": {
            (start + timedelta(days=index)).isoformat(): {"123": 100}
            for index in range(365)
        }}
        self.ns["invoice_import_log"] = [{
            "location": "Alice", "delivery_date": (start + timedelta(days=index)).isoformat(),
            "products": {"123.0": 1},
        } for index in range(364)]
        response = self.client.get(f"/api/reports/weekly-usage?start_date={start}&end_date={end}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["windows_used"], 52)
        self.assertEqual(sum(row["usage"] for row in payload["rows"]), 364)
        self.assertEqual(payload["rows"][-1]["avg_daily_usage_4w"], 1)
        self.assertEqual(payload["rows"][-1]["target_stock"], 10)
        dates = [day["date"] for row in payload["rows"] for day in row["usage_daily"]]
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(dates[0], str(start))
        self.assertEqual(dates[-1], str(end))

        partial = self.client.get(
            "/api/reports/weekly-usage?start_date=2026-01-06&end_date=2026-01-14"
        ).get_json()
        self.assertEqual(sum(row["window_days"] for row in partial["rows"]), 9)
        self.assertEqual(sum(row["usage"] for row in partial["rows"]), 9)
        self.assertEqual(partial["rows"][-1]["avg_daily_usage_4w"], 1)

    def test_predictive_report_reads_files_and_excludes_negative_anomalies(self):
        start = date(2026, 1, 4)
        end = start + timedelta(days=363)
        inventory = {"Alice": {}, "Kingsville": {}}
        invoices = []
        for index in range(365):
            day = start + timedelta(days=index)
            inventory["Alice"][str(day)] = {"123.0": 100 if index == 0 else 101, "456": 100}
            if index < 364:
                invoices.append({
                    "location": "Alice", "delivery_date": str(day),
                    "products": {"123.0": 0 if index == 0 else day.weekday() + 1, "456": 0.5},
                })
        invoices.append({"location": "Kingsville", "delivery_date": str(start), "products": {"123": 999}})
        invoices[0]["line_items"] = [{"raw_product_number": "456.0", "quantity": 999}]
        self.save_data(inventory, invoices)
        self.ns["products_list"] = [
            {"Product Number": "123", "Product Description": "Burger"},
            {"Product Number": "456.0", "Product Description": "Fries"},
            {"Product Number": "789", "Product Description": "No counts"},
        ]
        self.ns["inventory_data"] = {"Alice": {str(start): {"123": 999}}}
        response = self.client.get(f"/api/reports/predictive-par-levels?start_date={start}&end_date={end}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total_products"], 3)
        self.assertEqual([row["product_number"] for row in payload["rows"]], ["123", "456", "789"])
        burger, fries, missing = payload["rows"]
        expected_avg = (52 * 28 - 7) / 363
        self.assertAlmostEqual(burger["avg_daily_usage"], expected_avg, places=4)
        self.assertAlmostEqual(burger["target_stock"], expected_avg * 6, places=4)
        self.assertAlmostEqual(burger["weekly_demand"], expected_avg * 7, places=4)
        self.assertEqual(burger["velocity_band"], "fast")
        self.assertEqual(burger["anomaly_days_excluded"], 1)
        self.assertEqual(burger["sample_days"], 363)
        self.assertEqual(burger["weekday_sample_days"]["sunday"], 51)
        self.assertEqual([burger[f"avg_{weekday}_usage"] for weekday in (
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        )], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(fries["velocity_band"], "medium")
        self.assertEqual(fries["target_stock"], 5)
        self.assertIsNone(missing["avg_daily_usage"])
        self.assertIsNone(missing["target_stock"])
        self.assertEqual(missing["coverage_status"], "insufficient_data")
        self.assertEqual(missing["unavailable_days"], 364)

        exported = self.client.get(
            f"/api/reports/predictive-par-levels?start_date={start}&end_date={end}&format=csv"
        )
        self.assertEqual(exported.status_code, 200)
        csv_rows = list(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
        self.assertEqual(len(csv_rows), 3)
        self.assertEqual(float(csv_rows[0]["target_stock"]), burger["target_stock"])
        self.assertEqual(csv_rows[2]["target_stock"], "")

    def test_leap_year_and_default_52_week_ranges(self):
        self.save_data({"Alice": {
            "2024-01-01": {"123": 366}, "2025-01-01": {"123.0": 0},
        }}, [])
        leap_year = self.client.get(
            "/api/reports/predictive-par-levels?start_date=2024-01-01&end_date=2024-12-31"
        ).get_json()
        product = leap_year["rows"][0]
        self.assertEqual(leap_year["calendar_days"], 366)
        self.assertEqual(product["sample_days"], 366)
        self.assertEqual(product["total_usage"], 366)
        self.assertEqual(product["avg_daily_usage"], 1)
        self.assertEqual(product["target_stock"], 10)
        self.assertEqual(product["estimated_days"], 366)
        self.assertEqual(sum(product["weekday_sample_days"].values()), 366)
        default_report = self.client.get("/api/reports/predictive-par-levels").get_json()
        self.assertEqual(default_report["calendar_days"], 364)
        self.assertEqual(default_report["end_date"], str(date.today() - timedelta(days=1)))

    def test_activity_missing_counts_is_unavailable_not_zero_usage(self):
        self.ns["inventory_data"] = {"Alice": {"2026-01-03": {"123": 0}}}
        payload = self.client.get(
            "/api/reports/product-activity?start_date=2026-01-01&end_date=2026-01-03"
        ).get_json()
        product = payload["products"][0]
        self.assertIsNone(product["usage"])
        self.assertIsNone(product["cases_required"])
        self.assertEqual(product["usage_summary"]["covered_days"], 0)

    def test_predictive_invalid_sources_fail_explicitly_and_zero_usage_is_valid(self):
        self.save_data({"Alice": {
            "2026-01-01": {"123": 1}, "2026-01-04": {"123": 1},
        }}, [])
        payload = self.client.get(
            "/api/reports/predictive-par-levels?start_date=2026-01-01&end_date=2026-01-03"
        ).get_json()
        product = payload["rows"][0]
        self.assertEqual(product["avg_daily_usage"], 0)
        self.assertEqual(product["target_stock"], 0)
        self.assertEqual(product["estimated_days"], 3)
        self.assertEqual(product["velocity_band"], "slow")

        for query in ("start_date=bad", "start_date=2026-01-04&end_date=2026-01-01", "format=xml"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/reports/predictive-par-levels?" + query).status_code, 400)
        self.save_data({"Alice": {"2026-01-01": {"123": "not-a-quantity"}}}, [])
        with self.assertLogs(level="ERROR"):
            self.assertEqual(self.client.get("/api/reports/predictive-par-levels").status_code, 422)
        (self.data_dir / "inventory_database.json").unlink()
        with self.assertLogs(level="ERROR"):
            self.assertEqual(self.client.get("/api/reports/predictive-par-levels").status_code, 503)

    def test_velocity_boundaries_and_runtime_profile_delegation(self):
        for daily, expected in (
            (0.49, ("slow", 15, 18)), (0.5, ("medium", 10, 12)),
            (1.99, ("medium", 10, 12)), (2, ("fast", 6, 7)),
        ):
            with self.subTest(daily=daily):
                self.assertEqual(self.ns["_usage_velocity_profile"](daily), expected)
        self.ns["_velocity_profile"] = lambda daily: ("fast", 9, 11)
        self.assertEqual(self.ns["_usage_velocity_profile"](3), ("fast", 9, 11))
        self.ns["_velocity_profile"] = lambda daily: ("bad-band", 9, 11)
        with self.assertRaises(ValueError):
            self.ns["_usage_velocity_profile"](3)


if __name__ == "__main__":
    unittest.main()
