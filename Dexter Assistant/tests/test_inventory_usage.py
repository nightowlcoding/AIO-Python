import ast
import csv
import io
import importlib.util
import json
import logging
import marshal
import math
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape, unescape
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
            "_rewrite_weekly_usage_display", "_rewrite_product_activity_display",
            "_rewrite_price_report_location", "_normalize_runtime_location_text",
            "_dexter_selected_location_from_headers", "_dexter_selected_restaurant_id_from_headers",
            "_collect_requested_location_values", "_install_dexter_location_guard_patch",
        }
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual({node.name for node in functions}, names)
        self.ns = {
            "date": date, "datetime": datetime, "timedelta": timedelta,
            "defaultdict": defaultdict, "bisect_left": bisect_left, "bisect_right": bisect_right,
            "math": math, "re": re, "json": json, "csv": csv, "io": io, "logging": logging,
            "_html_escape": escape, "_html_unescape": unescape,
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

    def test_weekly_missing_counts_assume_zero_at_window_boundaries(self):
        self.ns["invoice_import_log"] = [
            {"location": "Alice", "delivery_date": "2026-01-04", "products": {"123": 7}},
            {"location": "Alice", "delivery_date": "2026-01-11", "products": {"123": 14}},
        ]
        payload = self.client.get(
            "/api/reports/weekly-usage?start_date=2026-01-04&end_date=2026-01-17"
        ).get_json()
        first, second = payload["rows"]
        self.assertEqual((first["beginning_inventory"], first["ending_inventory"], first["usage"]), (0, 0, 7))
        self.assertEqual((second["beginning_inventory"], second["ending_inventory"], second["usage"]), (0, 0, 14))
        self.assertEqual(second["avg_daily_usage_4w"], 1.5)
        self.assertEqual(second["avg_8day_usage_4w"], 12)
        self.assertEqual(first["usage_summary"]["assumed_zero_days"], 7)
        self.assertEqual(first["beginning_inventory_source"], "assumed_zero")
        self.assertEqual(first["ending_inventory_source"], "assumed_zero")
        self.assertIsNone(first["days_of_supply"])
        self.assertIsNone(first["suggested_order_qty"])
        self.assertIsNone(first["on_hand_value"])
        self.assertIsNone(first["do_not_order"])
        self.assertEqual(payload["latest_averages"]["123"]["assumed_zero_days"], 14)
        exported = self.client.get(
            "/api/reports/weekly-usage/export?start_date=2026-01-04&end_date=2026-01-17&layout=windows"
        )
        self.assertEqual(exported.status_code, 200)
        csv_rows = list(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
        self.assertEqual([float(row["usage"]) for row in csv_rows], [7, 14])
        self.assertEqual([int(row["assumed_zero_days"]) for row in csv_rows], [7, 7])
        self.assertEqual(csv_rows[0]["ending_inventory_source"], "assumed_zero")
        self.assertEqual(csv_rows[0]["suggested_order_qty"], "")
        self.assertEqual(self.client.get("/api/reports/weekly-usage/export").status_code, 400)
        summary = list(csv.DictReader(io.StringIO(self.client.get(
            "/api/reports/weekly-usage/export?start_date=2026-01-04&end_date=2026-01-17"
        ).get_data(as_text=True))))
        self.assertEqual(len(summary), 1)
        self.assertEqual((summary[0]["windows"], float(summary[0]["total_usage"])), ("2", 21))
        self.ns["inventory_data"] = {"Alice": {"2026-01-11": {"123": 4}}}
        payload = self.client.get(
            "/api/reports/weekly-usage?start_date=2026-01-04&end_date=2026-01-17"
        ).get_json()
        first, second = payload["rows"]
        self.assertEqual((first["beginning_inventory"], first["ending_inventory"], first["usage"]), (0, 4, 3))
        self.assertEqual((second["beginning_inventory"], second["ending_inventory"], second["usage"]), (4, 0, 18))
        self.assertEqual(first["ending_inventory_source"], "counted")
        self.assertEqual(second["beginning_inventory_source"], "counted")
        self.assertEqual(second["avg_daily_usage_4w"], 1.5)

    def test_weekly_latest_average_includes_omitted_zero_windows(self):
        self.ns["invoice_import_log"] = [
            {"location": "Alice", "delivery_date": "2026-01-04", "products": {"123": 7}},
        ]
        payload = self.client.get(
            "/api/reports/weekly-usage?start_date=2026-01-04&end_date=2026-02-07"
        ).get_json()
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["avg_daily_usage_4w"], 1)
        self.assertEqual(payload["latest_averages"]["123"]["avg_daily_usage_4w"], 0)
        self.assertEqual(payload["latest_averages"]["123"]["assumed_zero_days"], 35)

    def test_weekly_prices_use_latest_matching_invoice_at_each_window_end(self):
        self.ns["inventory_data"] = {"Alice": {
            "2026-01-04": {"123": 10}, "2026-01-18": {"123": 10},
        }}
        self.ns["invoice_import_log"] = [
            {"location": "Alice", "delivery_date": "2026-01-18",
             "products": {}, "product_prices": {"123": 3.33333}},
            {"location": "Alice", "delivery_date": "2026-01-10",
             "products": {}, "product_prices": {"123": 1}},
            {"location": "Alice", "delivery_date": "2026-01-10",
             "products": {}, "product_prices": {"123.0": 2}},
            {"location": "Kingsville", "delivery_date": "2026-01-11",
             "products": {}, "product_prices": {"123": 99}},
            {"location": "Alice", "delivery_date": "2026-01-19",
             "products": {}, "product_prices": {"123": 42}},
        ]
        url = "/api/reports/weekly-usage?start_date=2026-01-04&end_date=2026-01-17"
        rows = self.client.get(url).get_json()["rows"]
        self.assertEqual([row["unit_cost"] for row in rows], [2, 3.3333])
        self.assertEqual([row["on_hand_value"] for row in rows], [20, 33.33])

        exported = self.client.get(url.replace("weekly-usage?", "weekly-usage/export?layout=windows&"))
        csv_rows = list(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
        self.assertEqual([float(row["unit_cost"]) for row in csv_rows], [2, 3.3333])

    def test_weekly_assumptions_do_not_replace_real_count_intervals(self):
        self.ns["inventory_data"] = {"Alice": {
            "2026-01-07": {"123": 4}, "2026-01-09": {"123": 2},
        }}
        self.ns["invoice_import_log"] = [
            {"location": "Alice", "delivery_date": "2026-01-04", "products": {"123": 7}},
            {"location": "Alice", "delivery_date": "2026-01-08", "products": {"123": 1}},
        ]
        payload = self.client.get(
            "/api/reports/weekly-usage?start_date=2026-01-04&end_date=2026-01-10"
        ).get_json()
        row = payload["rows"][0]
        self.assertEqual(row["usage"], 8)
        self.assertEqual(row["usage_summary"]["assumed_zero_days"], 5)
        self.assertEqual([day["calculation_mode"] for day in row["usage_daily"]], [
            "assumed_zero", "assumed_zero", "assumed_zero", "estimated_gap",
            "estimated_gap", "assumed_zero", "assumed_zero",
        ])

    def test_activity_display_limits_descriptions_and_keeps_full_text(self):
        node = shutil.which("node")
        bytecode = ROOT / "Inventory Control 3" / "app.pyc"
        if not node or bytecode.read_bytes()[:4] != importlib.util.MAGIC_NUMBER:
            self.skipTest("Node and the matching application bytecode are required")
        with bytecode.open("rb") as source:
            source.read(16)
            code = marshal.load(source)

        def find_html(code_object):
            for value in code_object.co_consts:
                if isinstance(value, types.CodeType):
                    found = find_html(value)
                    if found:
                        return found
                elif isinstance(value, str) and "function displayProductActivityReport(data) {" in value:
                    return value
            return None

        original = find_html(code)
        self.assertIsNotNone(original)
        with self.assertNoLogs(level="WARNING"):
            rewritten = self.ns["_rewrite_product_activity_display"](original)
        start = rewritten.index("function displayProductActivityReport(data) {")
        end = rewritten.index("function generateWeeklyUsageReport()", start)
        script = r"""
const vm = require('vm');
const source = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const container = {};
const escape = value => String(value ?? '').replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
const context = {
    document: {getElementById: () => container},
    initializeReportQuickEditHandlers: () => {},
    escapeHtml: escape, escapeAttr: escape,
    formatReportQuickValue: value => String(value),
    buildReportQuickCell: () => 'editable',
};
vm.createContext(context);
vm.runInContext(source, context);
const descriptions = ['Short', '12345678901234567890', '1234567890123456789"<more'];
const products = descriptions.map((description, i) => ({
    product_number: String(i), description, brand: 'Brand', package_size: '4/5 LB',
    inventory_dates: [], order_dates: []
}));
context.displayProductActivityReport({
    products, total_products: products.length, location: 'Alice',
    date_range: {start: '2026-01-01', end: '2026-01-02'}
});
const html = container.innerHTML;
if (!html.includes('title="Short" aria-label="Short" tabindex="0"><span class="ic3-description-short" aria-hidden="true">Short</span>'))
    throw Error('short description');
if (!html.includes('<span class="ic3-description-short" aria-hidden="true">12345678901234567890</span>'))
    throw Error('exact-length description');
if (!html.includes('title="1234567890123456789&quot;&lt;more" aria-label="1234567890123456789&quot;&lt;more"'))
    throw Error('long description or unsafe title');
if (!html.includes('<span class="ic3-description-short" aria-hidden="true">1234567890123456789…</span>') ||
    !html.includes('<span class="ic3-description-full" aria-hidden="true">1234567890123456789&quot;&lt;more</span>'))
    throw Error('long description is not truncated and expandable');
if (!html.includes('editable')) throw Error('package quick edit lost');
"""
        result = subprocess.run(
            [node, "-e", script], input=json.dumps(rewritten[start:end]),
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_price_report_location_matches_portal_scope(self):
        html = (
            '<select id="priceReportLocation">'
            '<option value="all">All Locations</option>'
            '<option value="Kingsville">Kingsville</option>'
            '<option value="Alice">Alice</option></select>'
        )
        rewrite = self.ns["_rewrite_price_report_location"]
        self.assertEqual(rewrite(html, ""), html)
        self.assertEqual(
            rewrite(html, "Alice Main"),
            '<select id="priceReportLocation"><option value="Alice">Alice</option></select>',
        )
        self.assertEqual(
            rewrite(html, 'Other & "More"'),
            '<select id="priceReportLocation"><option value="Other &amp; &quot;More&quot;">'
            'Other &amp; &quot;More&quot;</option></select>',
        )

        self.ns["app"] = self.app
        self.ns["_install_dexter_location_guard_patch"]()
        self.app.add_url_rule(
            "/api/reports/price-fluctuations",
            "price_report_test",
            lambda: jsonify({"success": True}),
        )
        headers = {"X-Dexter-Restaurant-Location": "Alice"}
        self.assertEqual(
            self.client.get("/api/reports/price-fluctuations?location=all", headers=headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/reports/price-fluctuations?location=Kingsville", headers=headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/reports/price-fluctuations?location=Alice", headers=headers).status_code,
            200,
        )

    def test_weekly_display_distinguishes_missing_counts_from_zero(self):
        node = shutil.which("node")
        bytecode = ROOT / "Inventory Control 3" / "app.pyc"
        if not node or bytecode.read_bytes()[:4] != importlib.util.MAGIC_NUMBER:
            self.skipTest("Node and the matching application bytecode are required")
        with bytecode.open("rb") as source:
            source.read(16)
            code = marshal.load(source)

        def find_html(code_object):
            for value in code_object.co_consts:
                if isinstance(value, types.CodeType):
                    found = find_html(value)
                    if found:
                        return found
                elif isinstance(value, str) and "function displayWeeklyUsageReport(data) {" in value:
                    return value
            return None

        original = find_html(code)
        self.assertIsNotNone(original)
        with self.assertNoLogs(level="WARNING"):
            rewritten = self.ns["_rewrite_weekly_usage_display"](original)
        start = rewritten.index("function displayWeeklyUsageReport(data) {")
        end = rewritten.index("function setWeeklyUsageView(viewName) {", start)
        script = r"""
const vm = require('vm');
const source = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const container = {};
const context = {document: {getElementById: () => container},
                 escapeHtml: x => x, currentWeeklyUsageView: 'summary'};
vm.createContext(context);
vm.runInContext(source, context);
const row = (id, begin, end, usage, avg, covered) => ({
    product_number: id, description: id, group: '',
    window_start: '2026-01-01', window_end: '2026-01-03',
    beginning_inventory: begin, ending_inventory: end, total_orders: 2,
    usage, avg_8day_usage_4w: avg, avg_daily_usage_4w: avg,
    usage_summary: {covered_days: covered, unavailable_days: 2 - covered, assumed_zero_days: 0}
});
const data = {location: 'Alice', start_date: '2026-01-01', end_date: '2026-01-02',
              windows_used: 1, windows_skipped: 2,
              rows: [row('missing', null, null, null, null, 0),
                     row('zero', 0, 0, 0, 0, 2),
                     row('partial', 3, 2, 1, 0.5, 1)]};
function cells(id) {
    const rows = [...container.innerHTML.matchAll(/<tr>([\s\S]*?)<\/tr>/g)];
    const row = rows.find(match => match[1].includes('>' + id + '</td>'));
    if (!row) throw Error('missing row ' + id);
    return [...row[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(match => match[1]);
}
context.displayWeeklyUsageReport(data);
if (!container.innerHTML.includes('Windows Used:</strong> 1') ||
    !container.innerHTML.includes('Product-window rows omitted:</strong> 2') ||
    container.innerHTML.includes('undefined')) throw Error('bad window counts');
if (cells('missing').slice(6).join('|') !== '0|—|2|—|—|—|—') throw Error('missing displayed as zero');
if (cells('zero').slice(6).join('|') !== '0|0|2|0|0|0|0') throw Error('valid zero lost');
if (cells('partial')[10] !== '—') throw Error('partial usage shown as full total');
context.currentWeeklyUsageView = 'raw';
context.displayWeeklyUsageReport(data);
if (cells('missing').slice(5).join('|') !== '0|—|2|—|—|—|—') throw Error('raw missing displayed as zero');
data.windows_used = [{}, {}];
data.windows_skipped = [{window_start: '2026-01-01', window_end: '2026-01-02'}];
context.displayWeeklyUsageReport(data);
if (!container.innerHTML.includes('Windows Used:</strong> 2') ||
    !container.innerHTML.includes('Product-window rows omitted:</strong> 1')) throw Error('bad array window counts');
"""
        result = subprocess.run(
            [node, "-e", script], input=json.dumps(rewritten[start:end]),
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
