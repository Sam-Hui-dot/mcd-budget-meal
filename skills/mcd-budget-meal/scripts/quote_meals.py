#!/usr/bin/env python3
"""Quote up to three prepared baskets, normalize official totals and compare them."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from compare_meals import (amount_cents, check_preferences, compare, constraints,
                           integer, markdown, meal_items, strings, text_value)
from mcp_query import Client, authorization, error_message, structured_result
from report_meals import html_report

SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
SKILL_MARKER = Path("skills") / "mcd-budget-meal" / "SKILL.md"


def project_root(script_root=None):
    """Directory whose private/ holds raw records.

    Running from a repository checkout keeps records in <repo>/private/. Installed
    under a skills directory, records stay in the skill's own private/, so they can
    be found and deleted without writing into an unrelated parent directory.
    """
    root = Path(script_root or SCRIPT_ROOT)
    repository = root.parents[2]
    if (repository / SKILL_MARKER).is_file() and (repository / "README.md").is_file():
        return repository
    return root.parent


PROJECT_ROOT = project_root()


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def private_path(path):
    """Full tool records can only be written under this checkout's ignored private/."""
    root = (PROJECT_ROOT / "private").resolve()
    destination = path.resolve()
    if destination == root or root not in destination.parents:
        raise ValueError("原始记录只能写入本项目 private/ 内的子目录")
    return destination


def request_contents(arguments):
    """Read actual codes and quantities from a fully specified official request.

    Combo parents are limited to quantity=1: multiple-parent round quantity
    semantics have not been live verified. Standalone quantities may exceed one.
    """
    requested = arguments.get("items")
    if not isinstance(requested, list) or not requested:
        raise ValueError("核价 arguments.items 必须是非空数组")
    result = []
    for product in requested:
        if not isinstance(product, dict):
            raise ValueError("核价商品必须是对象")
        code = text_value(product.get("productCode"), "productCode")
        quantity = integer(product.get("quantity"), "quantity", 1)
        rounds = product.get("roundList")
        option = {"parent_modification": {}, "modification": product.get("modification", {})}
        if rounds is None:
            result.append((code, quantity, False, option))
            continue
        if quantity != 1:
            raise ValueError("批量入口暂只支持每个套餐父项 quantity=1；多份套餐需另行核实数量契约")
        if not isinstance(rounds, list) or not rounds:
            raise ValueError("套餐 roundList 需要完整的非空轮次数组")
        result.append((code, quantity, True, option))
        seen_rounds = set()
        for round_item in rounds:
            if not isinstance(round_item, dict):
                raise ValueError("套餐轮次必须是对象")
            round_code = text_value(round_item.get("round"), "round")
            if round_code in seen_rounds:
                raise ValueError("套餐轮次重复")
            seen_rounds.add(round_code)
            choices = round_item.get("comboItemList")
            if not isinstance(choices, list) or not choices:
                raise ValueError("每个套餐轮次需要实际已选子项")
            for choice in choices:
                if not isinstance(choice, dict):
                    raise ValueError("套餐子项必须是对象")
                result.append((text_value(choice.get("code"), "comboItemList.code"),
                               integer(choice.get("quantity"), "comboItemList.quantity", 1), False,
                               {"parent_modification": product.get("modification", {}),
                                "modification": choice.get("modification", {})}))
    return result


def bind_items(declared, arguments):
    """Bind display rows to request contents, generate option identities from input."""
    declared = meal_items(declared)
    request = request_contents(arguments)
    expected, actual = Counter(), Counter()
    names = {}
    for item in declared:
        key = (item["code"], item["container"])
        expected[key] += item["quantity"]
        names[key] = item["name"]
    for code, quantity, container, _ in request:
        actual[(code, container)] += quantity
    if expected != actual:
        raise ValueError("展示餐单的编码、组成或数量与核价请求不一致")
    return [{"code": code, "name": names[(code, container)], "quantity": quantity,
             "container": container, "option_key": digest(option)}
            for code, quantity, container, option in request]


def prepare_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("餐单计划必须是 JSON 对象")
    store = text_value(plan.get("store"), "store")
    if plan.get("data_kind") not in ("live", "demo"):
        raise ValueError("计划必须显式标注 data_kind 为 live 或 demo")
    if plan.get("mode") != "pickup":
        raise ValueError("批量入口仅支持现在、到店取餐")
    budget = integer(plan.get("budget_cents"), "budget_cents")
    rules = constraints(plan)
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 3:
        raise ValueError("每轮只允许 1–3 份候选")
    prepared, seen = [], set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("候选必须是对象")
        label = text_value(candidate.get("id"), "id")
        if label in seen:
            raise ValueError("候选 id 重复")
        seen.add(label)
        try:
            args = candidate.get("arguments")
            if not isinstance(args, dict):
                raise ValueError("每份候选必须有完整的 arguments 对象")
            if args.get("storeCode") != store or type(args.get("beType")) is not int or args.get("beType") != 1:
                raise ValueError("全部候选必须属于所选门店和到店取餐场景")
            if type(args.get("orderType")) is not int or args.get("orderType") != 1:
                raise ValueError("orderType 必须为 1")
            if any(key in args for key in ("beCode", "withOrder", "gmServiceCode", "reservationDate")):
                raise ValueError("本入口不支持预约、业务编码、团餐或随单购会员参数")
            items = bind_items(candidate.get("items"), args)
            check_preferences(items, rules)
            conditions = strings(candidate.get("conditions", []), "conditions")
            has_coupon = any("couponId" in item or "couponCode" in item for item in args["items"])
            for item in args["items"]:
                if "couponId" in item or "couponCode" in item:
                    text_value(item.get("couponId"), "couponId")
                    text_value(item.get("couponCode"), "couponCode")
            if has_coupon and not conditions:
                raise ValueError("使用券的候选必须写明本次门店适用条件")
        except ValueError as exc:
            # Keep the original reason; say which candidate failed so one bad row
            # never looks like a whole-plan failure.
            raise ValueError(f"候选 {label}：{exc}") from exc
        prepared.append({"id": label, "title": text_value(candidate.get("title"), "title"),
                         "items": items, "conditions": conditions, "arguments": args})
    output = {key: plan[key] for key in ("required_codes", "required_quantities", "excluded_codes",
                                        "excluded_terms", "required_groups") if key in plan}
    output.update({"data_kind": "live", "store": store, "mode": "pickup", "budget_cents": budget})
    return output, prepared


def schema_types(value, schema, path="arguments"):
    """Lightweight checks for the types/required/enums exposed by current schema.

    Not a full JSON Schema validator; final validation belongs to official MCP.
    """
    if not isinstance(schema, dict):
        raise ValueError("当前 inputSchema 结构不可用")
    kind = schema.get("type")
    checks = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
              "string": lambda x: isinstance(x, str), "integer": lambda x: type(x) is int,
              "number": lambda x: type(x) in (int, float), "boolean": lambda x: type(x) is bool,
              "null": lambda x: x is None}
    if isinstance(kind, str) and kind in checks and not checks[kind](value):
        raise ValueError(f"{path} 不符合当前 schema 的 {kind} 类型")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} 不在当前 schema 枚举中")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} 缺少当前 schema 必填参数")
        for key, child in value.items():
            if key in schema.get("properties", {}):
                schema_types(child, schema["properties"][key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{path}.{key} 不被当前 schema 允许")
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            schema_types(child, schema["items"], f"{path}[{index}]")


def price_unit(tool):
    field = tool.get("outputSchema", {}).get("properties", {}).get("data", {}).get("properties", {}).get("price", {})
    description = str(field.get("description", "")).replace(" ", "")
    if "单位分" not in description:
        raise ValueError("当前官方 outputSchema 未明确 data.price 单位为分；停止自动转换")
    return "cent"


def normalize(candidate, response, store, quoted_at, record_ref):
    payload = structured_result(response)
    data = payload.get("data")
    if not isinstance(data, dict) or "price" not in data:
        raise ValueError("官方返回缺少整单 data.price，不能当作零元")
    payable = amount_cents(data["price"], "cent")
    # If the server echoes selected top-level products, ensure it priced this basket.
    if "productList" in data:
        products = data["productList"]
        if not isinstance(products, list) or not products:
            raise ValueError("官方 productList 为空或结构变化")
        echoed, requested = Counter(), Counter()
        for product in products:
            if not isinstance(product, dict):
                raise ValueError("官方商品回显格式变化")
            echoed[text_value(product.get("productCode"), "response.productCode")] += integer(product.get("quantity"), "response.quantity", 1)
        for product in candidate["arguments"]["items"]:
            requested[product["productCode"]] += product["quantity"]
        if echoed != requested:
            raise ValueError("官方回显商品与请求不一致；本轮停止")
    return {"id": candidate["id"], "title": candidate["title"], "items": candidate["items"],
            "conditions": candidate["conditions"], "quote": {
                "status": "ok", "tool": "calculate-price", "store": store, "mode": "pickup",
                "currency": "CNY", "source_amount": data["price"], "source_unit": "cent",
                "payable_cents": payable, "quoted_at": quoted_at,
                "source_ref": record_ref, "amount_field": "result.structuredContent.data.price",
                "request_sha256": digest(candidate["arguments"])}}


def run(plan, client, records_dir=None, now=None):
    normalized, candidates = prepare_plan(plan)
    if plan["data_kind"] != "live":
        raise ValueError("模拟计划只可 --check-plan，不能发送官方请求")
    if records_dir is not None:
        records_dir = private_path(records_dir)
        if records_dir.exists() and any(records_dir.iterdir()):
            raise ValueError("记录目录已有文件，请为本轮使用新的 private/ 子目录")
        records_dir.mkdir(parents=True, exist_ok=True)
    client.initialize()
    definition = client.describe("calculate-price")
    price_unit(definition)
    for candidate in candidates:
        schema_types(candidate["arguments"], definition.get("inputSchema"))
    normalized["candidates"] = []
    stopped = False
    for position, candidate in enumerate(candidates, 1):
        clean = {key: candidate[key] for key in ("id", "title", "items", "conditions")}
        if stopped:
            clean["quote"] = {"status": "error", "reason": "此前调用失败，本轮停止；此候选未请求"}
            normalized["candidates"].append(clean)
            continue
        response = None
        quoted_at = (now or datetime.now(timezone.utc)).isoformat()
        reference = "local-request-sha256:" + digest(candidate["arguments"])
        try:
            response = client.call("calculate-price", candidate["arguments"])
            quoted_at = (now or datetime.now(timezone.utc)).isoformat()
            if records_dir:
                filename = records_dir / f"quote-{position}.json"
                record = {"recorded_at": quoted_at, "tool": "calculate-price", "arguments": candidate["arguments"],
                          "request_sha256": digest(candidate["arguments"]), "tool_definition": definition,
                          "response": response}
                filename.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                reference = str(filename.relative_to(PROJECT_ROOT))
            clean = normalize(candidate, response, normalized["store"], quoted_at, reference)
        except Exception as exc:
            stopped = True
            # Never include arbitrary remote exception strings or raw request data in public output.
            reason = error_message(exc)
            clean["quote"] = {"status": "error", "reason": reason}
        normalized["candidates"].append(clean)
    result = compare(normalized, now=now)
    if records_dir:
        # Presentation/export failures must never erase successful official quotes.
        warnings = []
        try:
            page = html_report(result, now)
            (records_dir / "meal-report.html").write_text(page, encoding="utf-8")
        except Exception:
            warnings.append("HTML报告未生成；有效报价仍保留。请检查本机报告模板和目录写入权限，可稍后从comparison.json恢复。")
        if warnings:
            result["warnings"] = warnings
        try:
            (records_dir / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            result.setdefault("warnings", []).append("比较JSON未保存；请保留终端输出并检查目录写入权限。已有报价未因此失效。")
    return normalized, result, stopped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Private JSON plan prepared from current menu/detail")
    parser.add_argument("--use-workbuddy-config", action="store_true")
    parser.add_argument("--server-key", help="Explicit official connector key when multiple are configured")
    parser.add_argument("--records-dir", type=Path, help="Fresh subdirectory under this project's private/")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--check-plan", action="store_true", help="Validate basket/preferences locally; no token or network")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    # Validate all baskets before loading credentials or contacting the server.
    _, candidates = prepare_plan(plan)
    if args.check_plan:
        print(json.dumps({"data_kind": plan["data_kind"], "store": plan["store"],
                          "budget_cents": plan["budget_cents"], "candidate_count": len(candidates),
                          "status": "本地计划检查通过；未核价、未读取凭证、未联网"}, ensure_ascii=False, indent=2))
        return 0
    if plan["data_kind"] != "live":
        raise ValueError("模拟计划禁止联网；请由当前真实菜单构造 live 计划")
    if args.server_key and not args.use_workbuddy_config:
        raise ValueError("--server-key需与--use-workbuddy-config一起使用。")
    _, result, stopped = run(plan, Client(authorization(args.use_workbuddy_config, args.server_key)), args.records_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else markdown(result), end="\n")
    return 1 if stopped or not result["summary"]["valid_distinct"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except Exception as exc:
        message = error_message(exc)
        print(json.dumps({"error_type": type(exc).__name__, "message": message}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
