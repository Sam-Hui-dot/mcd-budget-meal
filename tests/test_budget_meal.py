"""Offline regressions only. All MCP replies below are synthetic test fixtures."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "mcd-budget-meal" / "scripts"))
import quote_meals
from compare_meals import compare, markdown
from quote_meals import bind_items, normalize, prepare_plan, private_path, project_root, run, schema_types

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)


def demo():
    return json.loads((ROOT / "examples" / "demo-quotes.json").read_text(encoding="utf-8"))


def plan():
    value = json.loads((ROOT / "examples" / "plan-template.json").read_text(encoding="utf-8"))
    # These remain synthetic codes; FakeClient never opens a network connection.
    value["data_kind"] = "live"
    return value


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
    def initialize(self):
        pass
    def describe(self, tool):
        return {"name": tool, "inputSchema": {"type": "object"}, "outputSchema": {
            "properties": {"data": {"properties": {"price": {"description": "现价 单位分"}}}}}}
    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        return next(self.replies)


def reply(price=2300):
    return {"result": {"structuredContent": {"success": True, "data": {"price": price}}}}


class BudgetChecks(unittest.TestCase):
    def test_existing_demo_and_over_budget(self):
        result = compare(demo(), now=NOW)
        self.assertEqual([2300, 2850], [x["payable_cents"] for x in result["recommended"]])
        self.assertEqual(-250, result["over_budget"][0]["remaining_cents"])

    def test_required_quantity_rejects_single_burger(self):
        value = demo()
        value["required_quantities"] = {"DEMO-BURGER": 2}
        result = compare(value, now=NOW)
        self.assertEqual(0, result["summary"]["valid_distinct"])
        self.assertTrue(all("至少 2 份" in x["reason"] for x in result["excluded"]))

    def test_split_rows_count_toward_quantity(self):
        value = demo()
        candidate = value["candidates"][0]
        candidate["items"].append(copy.deepcopy(candidate["items"][0]))
        value["required_quantities"] = {"DEMO-BURGER": 2}
        self.assertEqual("demo-basic", compare(value, now=NOW)["recommended"][0]["id"])

    def test_alternative_group(self):
        value = demo()
        value["required_groups"] = [{"name": "饮料", "codes": ["DEMO-TEA", "DEMO-COLA"], "minimum": 1}]
        self.assertEqual(2, len(compare(value, now=NOW)["recommended"]))

    def test_excluded_names_and_codes(self):
        value = demo()
        value["excluded_terms"] = ["茶饮"]
        self.assertEqual(0, compare(value, now=NOW)["summary"]["valid_distinct"])
        value.pop("excluded_terms")
        value["excluded_codes"] = ["DEMO-FRIES-S"]
        self.assertEqual(1, compare(value, now=NOW)["summary"]["valid_distinct"])

    def test_conflicting_preferences(self):
        value = demo()
        value["excluded_codes"] = ["DEMO-BURGER"]
        with self.assertRaises(ValueError):
            compare(value, now=NOW)

    def test_missing_amount_never_becomes_free(self):
        value = demo()
        del value["candidates"][0]["quote"]["source_amount"]
        result = compare(value, now=NOW)
        self.assertEqual("demo-combo", result["recommended"][0]["id"])

    def test_amount_units_must_agree(self):
        value = demo()
        value["candidates"][0]["quote"]["source_unit"] = "cent"
        result = compare(value, now=NOW)
        self.assertIn("不一致", result["excluded"][0]["reason"])

    def test_stale_and_future_live_quotes(self):
        for offset in (-16, 2):
            value = demo()
            value["data_kind"] = "live"
            for candidate in value["candidates"]:
                candidate["quote"]["quoted_at"] = (NOW + timedelta(minutes=offset)).isoformat()
            self.assertEqual(0, compare(value, now=NOW)["summary"]["valid_distinct"])

    def test_wrong_store_is_excluded(self):
        value = demo()
        value["candidates"][0]["quote"]["store"] = "ANOTHER-STORE"
        self.assertEqual("demo-combo", compare(value, now=NOW)["recommended"][0]["id"])

    def test_same_contents_dedupe_despite_container(self):
        value = demo()
        duplicate = copy.deepcopy(value["candidates"][0])
        duplicate["id"] = "duplicate"
        duplicate["items"].append({"code": "OTHER-PARENT", "name": "另一套餐名", "quantity": 1, "container": True})
        value["candidates"].append(duplicate)
        self.assertEqual(3, compare(value, now=NOW)["summary"]["valid_distinct"])

    def test_all_over_budget_has_explicit_message(self):
        value = demo()
        value["budget_cents"] = 1000
        result = compare(value, now=NOW)
        self.assertFalse(result["recommended"])
        self.assertIn("全部超预算", markdown(result))

    def test_invalid_item_is_excluded_without_crash(self):
        value = demo()
        value["candidates"][0]["items"] = [None]
        self.assertEqual("demo-combo", compare(value, now=NOW)["recommended"][0]["id"])


def skill_tree(base, readme=False):
    """Synthetic skill layout: <base>/skills/mcd-budget-meal/scripts, plus optional README.md."""
    scripts = Path(base) / "skills" / "mcd-budget-meal" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts.parent / "SKILL.md").write_text("---\nname: mcd-budget-meal\n---\n", encoding="utf-8")
    if readme:
        Path(base, "README.md").write_text("# synthetic checkout\n", encoding="utf-8")
    return scripts


class PlanDiagnostics(unittest.TestCase):
    def test_binding_error_names_the_candidate(self):
        value = plan()
        value["candidates"][0]["id"] = "combo-a"
        value["candidates"][0]["items"][0]["quantity"] = 2
        with self.assertRaisesRegex(ValueError, r"候选 combo-a：.*不一致"):
            prepare_plan(value)

    def test_preference_error_names_the_candidate_and_keeps_reason(self):
        value = plan()
        value["candidates"][0]["id"] = "basic"
        value["required_quantities"] = {"DEMO-BURGER": 2}
        with self.assertRaisesRegex(ValueError, r"候选 basic：.*至少 2 份，实际 1 份"):
            prepare_plan(value)

    def test_second_candidate_is_named_not_the_first(self):
        value = plan()
        value["candidates"][0]["id"] = "first"
        extra = copy.deepcopy(value["candidates"][0])
        extra["id"] = "second"
        extra["items"][0]["quantity"] = 2
        value["candidates"].append(extra)
        with self.assertRaisesRegex(ValueError, r"候选 second：") as caught:
            prepare_plan(value)
        self.assertNotIn("候选 first", str(caught.exception))

    def test_installed_skill_keeps_records_inside_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            scripts = skill_tree(home / ".workbuddy")
            self.assertEqual(scripts.parent, project_root(scripts))
            with patch.object(quote_meals, "PROJECT_ROOT", scripts.parent):
                self.assertEqual(scripts.parent / "private" / "run-001",
                                 private_path(scripts.parent / "private" / "run-001"))
                with self.assertRaises(ValueError):
                    private_path(home / "private" / "run-001")

    def test_repository_checkout_keeps_existing_private_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp).resolve() / "repo"
            scripts = skill_tree(repository, readme=True)
            self.assertEqual(repository, project_root(scripts))
            with patch.object(quote_meals, "PROJECT_ROOT", repository):
                self.assertEqual(repository / "private" / "run-001",
                                 private_path(repository / "private" / "run-001"))
                with self.assertRaises(ValueError):
                    private_path(Path(tmp).resolve() / "elsewhere" / "private" / "run-001")


class WorkflowChecks(unittest.TestCase):
    def test_binds_display_to_request(self):
        value = plan()
        value["candidates"][0]["items"][0]["quantity"] = 2
        with self.assertRaisesRegex(ValueError, "不一致"):
            prepare_plan(value)

    def test_parent_not_a_second_burger(self):
        args = {"items": [{"productCode": "C", "quantity": 1, "roundList": [
            {"round": "1", "comboItemList": [{"code": "B", "quantity": 1}]}]}]}
        rows = [{"code": "C", "name": "套餐", "quantity": 1, "container": True},
                {"code": "B", "name": "汉堡", "quantity": 1}]
        result = bind_items(rows, args)
        self.assertEqual(1, sum(x["quantity"] for x in result if not x["container"]))

    def test_changed_modification_changes_basket_identity(self):
        value = plan()["candidates"][0]
        original = bind_items(value["items"], value["arguments"])
        value["arguments"]["items"][0]["modification"] = {"values": [{"code": "S", "key": "NO", "quantity": 1}]}
        changed = bind_items(value["items"], value["arguments"])
        self.assertNotEqual(original[0]["option_key"], changed[0]["option_key"])

    def test_demo_cannot_call_server(self):
        value = plan()
        value["data_kind"] = "demo"
        fake = FakeClient([])
        with self.assertRaises(ValueError):
            run(value, fake, now=NOW)
        self.assertFalse(fake.calls)

    def test_three_baskets_stop_after_first_business_failure(self):
        value = plan()
        for number in (2, 3):
            extra = copy.deepcopy(value["candidates"][0])
            extra["id"] = str(number)
            value["candidates"].append(extra)
        fake = FakeClient([{"result": {"structuredContent": {"success": False}}}])
        _, result, stopped = run(value, fake, now=NOW)
        self.assertTrue(stopped)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual(3, len(result["excluded"]))

    def test_success_before_failure_is_preserved(self):
        value = plan()
        second = copy.deepcopy(value["candidates"][0])
        second["id"] = "second"
        value["candidates"].append(second)
        fake = FakeClient([reply(), {"error": {"code": -1}}])
        normalized, result, stopped = run(value, fake, now=NOW)
        self.assertTrue(stopped)
        self.assertEqual(2300, result["recommended"][0]["payable_cents"])
        self.assertIn("request_sha256", normalized["candidates"][0]["quote"])

    def test_response_missing_price_and_failed_rpc_are_rejected(self):
        _, candidates = prepare_plan(plan())
        for response in ({"result": {"structuredContent": {"success": True, "data": {}}}},
                         {"error": {"code": -1}}, reply(True)):
            with self.assertRaises(ValueError):
                normalize(candidates[0], response, "DEMO-STORE", NOW.isoformat(), "synthetic")

    def test_server_echo_must_match_selected_basket(self):
        _, candidates = prepare_plan(plan())
        response = reply()
        response["result"]["structuredContent"]["data"]["productList"] = [{"productCode": "WRONG", "quantity": 1}]
        with self.assertRaisesRegex(ValueError, "不一致"):
            normalize(candidates[0], response, "DEMO-STORE", NOW.isoformat(), "synthetic")

    def test_schema_checks_nested_array_and_quantity_type(self):
        schema = {"type": "object", "required": ["items"], "properties": {"items": {
            "type": "array", "items": {"type": "object", "properties": {"quantity": {"type": "integer"}}}}}}
        for value in ({"items": "[]"}, {"items": [{"quantity": True}]}, {}):
            with self.assertRaises(ValueError):
                schema_types(value, schema)


if __name__ == "__main__":
    unittest.main()
