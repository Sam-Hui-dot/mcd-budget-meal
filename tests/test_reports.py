"""Offline report/diagnostic regressions; no real config, credentials or service."""
import copy
import json
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from test_budget_meal import ROOT, NOW, FakeClient, demo, plan, reply
import mcp_query
import quote_meals
from compare_meals import basket_difference, compare, markdown
from report_meals import html_report, report_data, snapshot_data, render


class Differences(unittest.TestCase):
    def test_added_counts_exclude_parent(self):
        result = compare(demo(), now=NOW)
        first = result["differences"][0]
        self.assertEqual(550, first["delta_cents"])
        self.assertEqual([{"name": "示例小份薯条", "quantity": 1}], first["added"])
        self.assertFalse(first["removed"])
        self.assertEqual(2, len(first["unchanged"]))
        self.assertIn("不是新增餐品的单独售价", markdown(result))

    def test_unlike_burgers_are_both_reported(self):
        result = compare(demo(), now=NOW)
        a, b = result["recommended"]
        b = copy.deepcopy(b)
        b["items"][1]["code"] = "OTHER-BURGER"
        b["items"][1]["name"] = "另一汉堡"
        difference = basket_difference(a, b)
        self.assertIn({"name": "示例汉堡", "quantity": 1}, difference["removed"])
        self.assertIn({"name": "另一汉堡", "quantity": 1}, difference["added"])

    def test_changed_options_not_claimed_unchanged(self):
        a = compare(demo(), now=NOW)["recommended"][0]
        b = copy.deepcopy(a)
        b["items"][0]["option_key"] = "another-option"
        difference = basket_difference(a, b)
        self.assertEqual(1, len(difference["added"]))
        self.assertEqual(1, len(difference["removed"]))


class ReportSafety(unittest.TestCase):
    def test_allowlist_omits_private_fields(self):
        result = compare(demo(), now=NOW)
        result["Authorization"] = "Bearer SECRET-TOKEN"
        result["recommended"][0]["source_ref"] = "PRIVATE-RECORD-PATH"
        result["recommended"][0]["couponId"] = "SECRET-COUPON"
        result["excluded"].append({"id": "x", "reason": "SECRET-RAW-ERROR"})
        page = html_report(result, NOW)
        for secret in ("SECRET-TOKEN", "PRIVATE-RECORD-PATH", "SECRET-COUPON", "SECRET-RAW-ERROR"):
            self.assertNotIn(secret, page)
        self.assertEqual(1, report_data(result, NOW)["excludedCount"])

    def test_data_cannot_break_out_of_script_tag(self):
        result = compare(demo(), now=NOW)
        result["recommended"][0]["title"] = '</script><img src=x onerror="bad()">&'
        page = html_report(result, NOW)
        embedded = re.search(r'<script id="mealReportData" type="application/json">(.*?)</script>', page, re.S).group(1)
        self.assertNotIn("<", embedded)
        self.assertEqual(result["recommended"][0]["title"], json.loads(embedded)["meals"][0]["title"])
        self.assertIn("connect-src 'none'", page)

    def test_empty_results_have_no_invented_meals(self):
        value = demo()
        value["required_quantities"] = {"NOT-IN-MENU": 1}
        data = report_data(compare(value, now=NOW), NOW)
        self.assertEqual([], data["meals"])
        self.assertEqual(3, data["excludedCount"])

    def test_js_unsafe_integer_is_rejected(self):
        result = compare(demo(), now=NOW)
        result["budget_cents"] = 2 ** 53
        with self.assertRaisesRegex(ValueError, "安全整数"):
            report_data(result, NOW)

    def test_historical_time_range_is_preserved(self):
        source = json.loads((ROOT / "examples/verified-snapshot.json").read_text(encoding="utf-8"))
        data = snapshot_data(source)
        self.assertEqual([1490, 2290, 2690], [m["variants"][0]["payableCents"] for m in data["meals"]])
        self.assertEqual(2290, data["meals"][1]["variants"][1]["payableCents"])
        self.assertTrue(all(v["quotedAt"] == source["window"] for m in data["meals"] for v in m["variants"]))
        self.assertIn("历史核价快照", render(data))

    def test_partial_failure_still_generates_report(self):
        value = plan()
        second = copy.deepcopy(value["candidates"][0])
        second["id"] = "second"
        value["candidates"].append(second)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            with patch.object(quote_meals, "PROJECT_ROOT", base):
                directory = base / "private" / "run"
                _, result, stopped = quote_meals.run(value, FakeClient([reply(), {"error": {"code": -1}}]), directory, NOW)
                self.assertTrue(stopped)
                page = (directory / "meal-report.html").read_text(encoding="utf-8")
                self.assertIn('"payableCents":2300', page)
                self.assertIn('"excludedCount":1', page)
                self.assertEqual(1, len(result["recommended"]))
                self.assertTrue((directory / "comparison.json").is_file())
                with self.assertRaisesRegex(ValueError, "已有文件"):
                    quote_meals.run(value, FakeClient([]), directory, NOW)


class Diagnostics(unittest.TestCase):
    def configure(self, home, servers):
        location = Path(home) / ".workbuddy" / "mcp.json"
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")

    def test_connector_can_have_different_name(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            self.configure(tmp, {"custom-name": {"url": mcp_query.ENDPOINT, "headers": {"authorization": "Bearer FAKE"}}})
            self.assertEqual("Bearer FAKE", mcp_query.authorization(True))

    def test_multiple_connectors_require_selection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            server = {"url": mcp_query.ENDPOINT, "headers": {"Authorization": "Bearer FAKE"}}
            self.configure(tmp, {"first": server, "second": server})
            with self.assertRaisesRegex(ValueError, "多个"):
                mcp_query.authorization(True)
            self.assertEqual("Bearer FAKE", mcp_query.authorization(True, "second"))

    def test_missing_config_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            with self.assertRaisesRegex(ValueError, "未找到"):
                mcp_query.authorization(True)

    def test_wrong_endpoint_and_placeholder_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            self.configure(tmp, {"wrong": {"url": "https://example.invalid", "headers": {"Authorization": "Bearer FAKE"}}})
            with self.assertRaisesRegex(ValueError, "未找到"):
                mcp_query.authorization(True)
            self.configure(tmp, {"official": {"url": mcp_query.ENDPOINT, "headers": {"Authorization": "Bearer ${TOKEN}"}}})
            with self.assertRaisesRegex(ValueError, "占位符"):
                mcp_query.authorization(True)

    def test_http_errors_do_not_expose_body_or_url(self):
        for status, expected in ((401, "认证"), (403, "认证"), (429, "限流"), (503, "暂时不可用")):
            error = urllib.error.HTTPError("https://secret.invalid/TOKEN", status, "RAW-SECRET", {}, None)
            message = mcp_query.error_message(error)
            self.assertIn(expected, message)
            self.assertNotIn("SECRET", message)
            self.assertNotIn("TOKEN", message)

    def test_rate_limit_stops_remaining_calls(self):
        class Limited(FakeClient):
            def call(self, tool, arguments):
                self.calls.append(tool)
                raise urllib.error.HTTPError(mcp_query.ENDPOINT, 429, "PRIVATE-BODY", {}, None)
        value = plan()
        second = copy.deepcopy(value["candidates"][0])
        second["id"] = "second"
        value["candidates"].append(second)
        client = Limited([])
        _, result, stopped = quote_meals.run(value, client, now=NOW)
        self.assertTrue(stopped)
        self.assertEqual(1, len(client.calls))
        self.assertIn("限流", result["excluded"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
