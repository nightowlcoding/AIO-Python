import ast
import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from flask import Flask, has_request_context, jsonify, request
from jinja2 import Environment, FileSystemLoader
from urllib.parse import urlencode, urlsplit
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("Requested functions were not found")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class IC3ReportPeriodTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.window_filter = Mock(side_effect=lambda rows, window: rows)
        self.namespace = load_functions(
            ROOT / "Inventory Control 3" / "app.py",
            ["_register_product_detail_endpoints"],
            {
                "jsonify": jsonify,
                "request": request,
                "_safe_parse_date": self.parse_date,
                "_effective_runtime_location": lambda: "Kingsville",
                "_canonical_product_number": lambda value: str(value).removesuffix(".0"),
                "_find_product_record_by_number": lambda products, number: {"Product Description": "Beef Cutlet"},
                "_window_filter_dates": self.window_filter,
                "products_list": [],
                "invoice_import_log": [],
                "order_data": {"Kingsville": {
                    "2026-09-01": {"123": 1},
                    "2026-09-02": {"123": 2.5, "123.0": 2.5},
                    "2026-09-03": {"123": 3},
                }, "Alice": {"2026-09-02": {"123": 999}}},
                "inventory_data": {"Kingsville": {
                    "2026-09-01": {"123": 1},
                    "2026-09-02": {"123": 0, "123.0": 0},
                    "2026-09-03": {"456": 10},
                }},
            },
        )
        self.namespace["_register_product_detail_endpoints"](self.app)
        self.client = self.app.test_client()

    @staticmethod
    def parse_date(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def test_inclusive_period_zero_counts_and_aliases(self):
        response = self.client.get("/api/products/123/detail?start_date=2026-09-02&end_date=2026-09-03")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["summary"]["total_order_qty"], 5.5)
        self.assertEqual(payload["summary"]["inventory_rows"], 1)
        self.assertEqual(payload["inventory_history"][0]["quantity"], 0)
        self.window_filter.assert_not_called()

    def test_open_bounds(self):
        for query, total in [("start_date=2026-09-02", 5.5), ("end_date=2026-09-02", 3.5)]:
            with self.subTest(query=query):
                payload = self.client.get("/api/products/123/detail?" + query).get_json()
                self.assertEqual(payload["summary"]["total_order_qty"], total)

    def test_invalid_or_reversed_dates(self):
        for query in ["start_date=bad", "end_date=2026-02-30", "start_date=2026-09-03&end_date=2026-09-01"]:
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/products/123/detail?" + query).status_code, 400)

    def test_existing_window_behavior(self):
        self.client.get("/api/products/123/detail?window=month")
        self.assertEqual(self.window_filter.call_count, 2)
        self.assertEqual(self.window_filter.call_args.args[1], "month")

    def test_explicit_blank_bounds_mean_all_history(self):
        payload = self.client.get("/api/products/123/detail?start_date=&end_date=").get_json()
        self.assertEqual(payload["summary"]["total_order_qty"], 6.5)
        self.window_filter.assert_not_called()

    def test_empty_period(self):
        payload = self.client.get("/api/products/123/detail?start_date=2027-01-01").get_json()
        self.assertEqual(payload["summary"]["total_order_qty"], 0)
        self.assertEqual(payload["summary"]["inventory_rows"], 0)


class ProductMixIC3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "test.db"
        self.app = Flask(__name__)
        self.restaurant = {"id": 1, "name": "BHB", "location": "Kingsville"}
        self.upstream = Mock()
        self.namespace = load_functions(
            ROOT / "ProductMixRestaurantDB" / "app.py",
            ["_init_ic3_item_links", "_ic3_product_number", "_get_ic3_catalog", "_get_ic3_item_history", "production_item_ic3"],
            {
                "app": self.app, "jsonify": jsonify, "request": request,
                "login_required": lambda function: function,
                "re": re, "datetime": datetime, "math": math,
                "_request_ic3_json": self.upstream,
                "get_db_connection": self.connect,
                "_resolve_report_restaurant": lambda raw: self.restaurant,
                "_get_selected_company_name": lambda: "BHB",
                "_has_access_to_restaurant_id": lambda number: number == 1,
                "_is_csrf_valid": lambda token: token == "test-token",
                "FORMULA_MODE": False,
            },
        )
        with self.connect() as conn:
            conn.execute("CREATE TABLE production_items (id INTEGER PRIMARY KEY, restaurant_id INTEGER)")
            conn.execute("INSERT INTO production_items VALUES (10, 1)")
            conn.execute("INSERT INTO production_items VALUES (20, 2)")
            self.namespace["_init_ic3_item_links"](conn)
        self.client = self.app.test_client()
        self.catalog = [{"Product Number": "123.0", "Product Description": "Beef Cutlet", "Product Package Size": "28 pieces"}]

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def save_link(self, number="123"):
        return self.client.post("/api/production-items/10/ic3?location_id=1", json={"action": "save", "product_number": number}, headers={"X-CSRF-Token": "test-token"})

    def history_payload(self):
        return {
            "success": True, "location": "Kingsville",
            "start_date": "2026-09-01", "end_date": "2026-09-03",
            "product": {"product_number": "123"},
            "order_history": [{"date": "2026-09-02", "quantity": 2.5, "location": "Kingsville"}],
            "inventory_history": [{"date": "2026-09-03", "quantity": 0, "location": "Kingsville"}],
            "summary": {"total_order_qty": 999},
        }

    def test_link_persists_and_remove_does_not_contact_ic3(self):
        self.upstream.return_value = self.catalog
        self.assertEqual(self.save_link().status_code, 200)
        with self.connect() as conn:
            link = dict(conn.execute("SELECT * FROM production_item_ic3_links").fetchone())
        self.assertEqual(link["ic3_product_number"], "123")
        self.assertEqual(link["description"], "Beef Cutlet")
        self.upstream.reset_mock()
        response = self.client.post("/api/production-items/10/ic3?location_id=1", json={"action": "remove"}, headers={"X-CSRF-Token": "test-token"})
        self.assertEqual(response.status_code, 200)
        self.upstream.assert_not_called()
        self.assertIsNone(self.client.get("/api/production-items/10/ic3?location_id=1").get_json()["link"])

    def test_missing_csrf_and_wrong_location_are_rejected(self):
        self.assertEqual(self.client.post("/api/production-items/10/ic3?location_id=1", json={"action": "remove"}).status_code, 400)
        self.assertEqual(self.client.get("/api/production-items/10/ic3?location_id=2").status_code, 403)
        self.assertEqual(self.client.get("/api/production-items/20/ic3?location_id=1").status_code, 404)
        self.assertEqual(self.client.get("/api/production-items/10/ic3?location_id=garbage").status_code, 403)
        self.upstream.assert_not_called()

    def test_product_must_exist_in_catalog(self):
        self.upstream.return_value = self.catalog
        self.assertEqual(self.save_link("999").status_code, 400)
        self.assertEqual(self.save_link("../api/inventory").status_code, 400)

    def test_history_totals_use_orders_and_preserve_zero_counts(self):
        self.upstream.return_value = self.history_payload()
        result = self.namespace["_get_ic3_item_history"](self.restaurant, "123", "2026-09-01", "2026-09-03")
        self.assertEqual(result["total_order_qty"], 2.5)
        self.assertEqual(result["inventory_count_dates"], 1)
        self.assertEqual(result["inventory_history"][0]["quantity"], 0)

    def test_wrong_product_location_period_and_bad_quantities_rejected(self):
        for mutation in [
            lambda body: body.update(location="Alice"),
            lambda body: body["product"].update(product_number="999"),
            lambda body: body.update(start_date=None),
            lambda body: body["order_history"][0].update(location="Alice"),
            lambda body: body["order_history"][0].update(date="2026-09-04"),
            lambda body: body["order_history"][0].update(quantity=float("nan")),
            lambda body: body["inventory_history"].append(dict(body["inventory_history"][0])),
        ]:
            with self.subTest(mutation=mutation):
                payload = self.history_payload()
                mutation(payload)
                self.upstream.return_value = payload
                with self.assertRaises(ValueError):
                    self.namespace["_get_ic3_item_history"](self.restaurant, "123", "2026-09-01", "2026-09-03")

    def test_outage_keeps_saved_link_and_has_no_fake_totals(self):
        self.upstream.return_value = self.catalog
        self.save_link()
        self.upstream.side_effect = ValueError("IC3 unavailable")
        payload = self.client.get("/api/production-items/10/ic3?location_id=1").get_json()
        self.assertEqual(payload["link"]["ic3_product_number"], "123")
        self.assertIsNone(payload["history"])
        self.assertIn("history_error", payload)

    def test_old_ic3_cannot_silently_return_recent_window_for_all_history(self):
        payload = self.history_payload()
        payload.pop("start_date")
        payload.pop("end_date")
        self.upstream.return_value = payload
        with self.assertRaisesRegex(ValueError, "needs an update"):
            self.namespace["_get_ic3_item_history"](self.restaurant, "123", "", "")

    def test_invalid_report_dates_never_contact_ic3(self):
        for query in ["start_date=bad", "start_date=2026-09-03&end_date=2026-09-01"]:
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/production-items/10/ic3?location_id=1&" + query).status_code, 400)
        self.upstream.assert_not_called()

    def test_company_mismatch_is_rejected(self):
        self.namespace["_get_selected_company_name"] = lambda: "Other company"
        self.assertEqual(self.client.get("/api/production-items/10/ic3?location_id=1").status_code, 403)
        self.upstream.assert_not_called()

    def test_changing_link_preserves_one_mapping_per_location_and_item(self):
        self.upstream.return_value = self.catalog
        self.save_link()
        self.upstream.return_value = [{"Product Number": "456", "Product Description": "Alternate Cutlet"}]
        self.assertEqual(self.save_link("456").status_code, 200)
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM production_item_ic3_links").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ic3_product_number"], "456")

    def test_focused_history_template_renders_and_escapes_names(self):
        environment = Environment(loader=FileSystemLoader(ROOT / "ProductMixRestaurantDB" / "templates"), autoescape=True)
        environment.filters["comma"] = str
        environment.get_template("reports_production.html")
        template = environment.get_template("_ic3_item_history.html")
        html = template.render(
            ic3_group={"production_item_id": 10, "production_item_name": "<script>bad</script>"},
            restaurant=self.restaurant,
            request={"headers": {"X-Dexter-Company-Name": "BHB"}},
            csrf_token="test-token",
            upload_filters={"location_id": "1", "start_date": "2026-09-01", "end_date": "2026-09-03"},
            url_for=lambda endpoint, **values: "/api/production-items/10/ic3?" + urlencode(values),
        )
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", html)
        self.assertIn("Saved Inventory Count Dates", html)
        self.assertIn("start_date=2026-09-01", html)
        self.assertIn('data-api-url="/app/productmix/api/production-items/', html)


class IC3TransportTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.namespace = load_functions(
            ROOT / "ProductMixRestaurantDB" / "app.py", ["_request_ic3_json"],
            {"app": self.app, "request": request, "has_request_context": has_request_context,
             "os": os, "json": json, "urllib_request": urllib_request, "urlsplit": urlsplit, "urlencode": urlencode},
        )
        self.restaurant = {"id": 1, "name": "BHB", "location": "Kingsville"}

    def test_portal_uses_authenticated_proxy_not_fixed_ic3_port(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'[]'
        with self.app.test_request_context(headers={"X-Dexter-Company-Name": "BHB", "Cookie": "dexter_session=test"}), patch.dict(os.environ, {"PM_DEXTER_BASE_URL": "http://127.0.0.1:5080", "PM_IC3_BASE_URL": ""}), patch.object(urllib_request, "build_opener") as build:
            build.return_value.open.return_value = response
            self.assertEqual(self.namespace["_request_ic3_json"](self.restaurant, "/api/products"), [])
            upstream_request = build.return_value.open.call_args.args[0]
            self.assertEqual(upstream_request.full_url, "http://127.0.0.1:5080/app/ic3/api/products?location_id=1")
            self.assertEqual(upstream_request.get_header("Cookie"), "dexter_session=test")
            self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 5)
            redirect_handler = build.call_args.args[0]
            self.assertIsNone(redirect_handler.redirect_request(None, None, 302, "", {}, "http://other.example"))

    def test_render_port_is_used_and_explicit_ic3_url_avoids_portal_hop(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'[]'
        with self.app.test_request_context(headers={"X-Dexter-Company-Name": "BHB", "Cookie": "dexter_session=test"}), patch.dict(os.environ, {"PORT": "10000", "DEXTER_PORT": "", "PM_DEXTER_BASE_URL": "", "PM_IC3_BASE_URL": ""}), patch.object(urllib_request, "build_opener") as build:
            os.environ.pop("PM_DEXTER_BASE_URL")
            build.return_value.open.return_value = response
            self.namespace["_request_ic3_json"](self.restaurant, "/api/products")
            self.assertTrue(build.return_value.open.call_args.args[0].full_url.startswith("http://127.0.0.1:10000/app/ic3/"))
            os.environ["PM_IC3_BASE_URL"] = "http://127.0.0.1:5003"
            self.namespace["_request_ic3_json"](self.restaurant, "/api/products")
            upstream_request = build.return_value.open.call_args.args[0]
            self.assertEqual(upstream_request.full_url, "http://127.0.0.1:5003/api/products")
            self.assertIsNone(upstream_request.get_header("Cookie"))

    def test_timeout_and_malformed_json_are_unavailable(self):
        with self.app.test_request_context(), patch.object(urllib_request, "build_opener") as build:
            build.return_value.open.side_effect = TimeoutError()
            with self.assertRaisesRegex(ValueError, "unavailable"):
                self.namespace["_request_ic3_json"](self.restaurant, "/api/products")
            build.return_value.open.side_effect = None
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b'not JSON'
            build.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "unavailable"):
                self.namespace["_request_ic3_json"](self.restaurant, "/api/products")


class ProductMixQueryIndexTests(unittest.TestCase):
    def test_normalized_name_indexes_are_selected_by_sqlite(self):
        namespace = load_functions(
            ROOT / "ProductMixRestaurantDB" / "app.py",
            ["_create_composite_indexes"],
            {},
        )
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.executescript(
            """
            CREATE TABLE production_items (id INTEGER, restaurant_id INTEGER, item_name TEXT);
            CREATE TABLE all_levels_items (id INTEGER, restaurant_id INTEGER, item_name TEXT);
            """
        )
        namespace["_create_composite_indexes"](conn.cursor())

        query_plans = {
            "production_items": conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM production_items "
                "WHERE restaurant_id = ? AND LOWER(TRIM(item_name)) = LOWER(TRIM(?))",
                (1, "Beef"),
            ).fetchall(),
            "all_levels_items": conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM all_levels_items "
                "WHERE restaurant_id = ? AND LOWER(TRIM(item_name)) = LOWER(TRIM(?))",
                (1, "Beef"),
            ).fetchall(),
        }

        self.assertTrue(
            any("idx_pi_restaurant_normalized_name" in row[3] for row in query_plans["production_items"])
        )
        self.assertTrue(
            any("idx_ali_restaurant_normalized_name" in row[3] for row in query_plans["all_levels_items"])
        )


if __name__ == "__main__":
    unittest.main()