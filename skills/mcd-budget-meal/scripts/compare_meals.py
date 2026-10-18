#!/usr/bin/env python3
"""Compare normalized quotes; does not connect to McDonald's or create orders."""

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from collections import Counter


def text_value(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip()


def integer(value, field, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} 必须是大于等于 {minimum} 的整数")
    return value


def strings(value, field):
    if not isinstance(value, list):
        raise ValueError(f"{field} 必须是字符串数组")
    return [text_value(item, field) for item in value]


def amount_cents(amount, unit):
    if isinstance(amount, bool) or not isinstance(amount, (str, int, float)):
        raise ValueError("source_amount 必须是数字或数字字符串")
    if unit not in ("yuan", "cent"):
        raise ValueError("source_unit 必须显式指定 yuan 或 cent")
    try:
        parsed = Decimal(str(amount))
    except InvalidOperation as exc:
        raise ValueError("source_amount 无法解析") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("source_amount 必须是有限的非负金额")
    converted = parsed * (100 if unit == "yuan" else 1)
    if converted != converted.to_integral_value():
        raise ValueError("source_amount 无法精确换算为整数分")
    return int(converted)


def time_value(value):
    try:
        result = datetime.fromisoformat(text_value(value, "quoted_at").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("quoted_at 必须是带时区的 ISO 时间") from exc
    if result.tzinfo is None:
        raise ValueError("quoted_at 缺少时区")
    return result


def meal_items(value):
    if not isinstance(value, list) or not value:
        raise ValueError("items 必须是非空餐品数组")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("餐品必须是对象")
        container = item.get("container", False)
        if type(container) is not bool:
            raise ValueError("container 必须为布尔值")
        option = item.get("option_key", "")
        if not isinstance(option, str):
            raise ValueError("option_key 必须是字符串")
        result.append({
            "code": text_value(item.get("code"), "item.code"),
            "name": text_value(item.get("name"), "item.name"),
            "quantity": integer(item.get("quantity"), "item.quantity", 1),
            "option_key": option,
            "container": container,
        })
    if not any(not item["container"] for item in result):
        raise ValueError("套餐必须列出实际组成")
    return result


def basket_key(items):
    quantities = {}
    for item in items:
        if item["container"]:
            continue
        key = (item["code"], item["option_key"], item["container"])
        quantities[key] = quantities.get(key, 0) + item["quantity"]
    return tuple(sorted((key, quantity) for key, quantity in quantities.items()))


def basket_difference(first, second):
    """Describe actual contents, without equating unlike burgers or valuing add-ons."""
    def quantities(plan):
        counts, names = Counter(), {}
        for item in plan["items"]:
            if not item.get("container", False):
                key = (item["code"], item.get("option_key", ""))
                counts[key] += item["quantity"]
                names[key] = item["name"]
        return counts, names
    before, before_names = quantities(first)
    after, after_names = quantities(second)
    def rows(counts, names):
        return [{"name": names[key], "quantity": count} for key, count in sorted(counts.items()) if count > 0]
    return {"from_id": first["id"], "to_id": second["id"],
            "from_title": first["title"], "to_title": second["title"],
            "delta_cents": second["payable_cents"] - first["payable_cents"],
            "added": rows(after - before, after_names), "removed": rows(before - after, before_names),
            "unchanged": rows(before & after, before_names),
            "conditions_changed": first["conditions"] != second["conditions"]}


def constraints(data):
    """Parse explicit preferences once, before accepting any candidate."""
    required = {code: 1 for code in strings(data.get("required_codes", []), "required_codes")}
    quantities = data.get("required_quantities", {})
    if not isinstance(quantities, dict):
        raise ValueError("required_quantities 必须是编码到最低数量的对象")
    for code, count in quantities.items():
        code = text_value(code, "required_quantities.code")
        required[code] = max(required.get(code, 0), integer(count, "required_quantities.count", 1))
    forbidden = set(strings(data.get("excluded_codes", []), "excluded_codes"))
    if forbidden.intersection(required):
        raise ValueError("同一餐品不能同时必选和排除")
    terms = strings(data.get("excluded_terms", []), "excluded_terms")
    groups = data.get("required_groups", [])
    if not isinstance(groups, list):
        raise ValueError("required_groups 必须是数组")
    normalized = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("required_groups 每项必须是对象")
        codes = set(strings(group.get("codes"), "required_groups.codes"))
        if not codes or not codes - forbidden:
            raise ValueError("必选类别需要至少一个未被排除的实际餐品编码")
        normalized.append({"name": text_value(group.get("name"), "required_groups.name"),
                           "codes": codes, "minimum": integer(group.get("minimum", 1), "required_groups.minimum", 1)})
    return {"required": required, "forbidden": forbidden, "terms": terms, "groups": normalized}


def check_preferences(items, rules):
    actual = [item for item in items if not item["container"]]
    counts = Counter()
    for item in actual:
        counts[item["code"]] += item["quantity"]
    for code, minimum in rules["required"].items():
        if counts[code] < minimum:
            raise ValueError(f"必选餐品 {code} 至少 {minimum} 份，实际 {counts[code]} 份")
    for item in items:
        if item["code"] in rules["forbidden"]:
            raise ValueError("包含排除餐品：" + item["name"])
    for item in actual:
        for term in rules["terms"]:
            if term.casefold() in item["name"].casefold():
                raise ValueError(f"餐品 {item['name']} 命中排除词：{term}")
    for group in rules["groups"]:
        count = sum(counts[code] for code in group["codes"])
        if count < group["minimum"]:
            raise ValueError(f"{group['name']} 至少 {group['minimum']} 份，实际 {count} 份")


def compare(data, max_age_minutes=15, now=None, *, historical=False):
    if not isinstance(data, dict):
        raise ValueError("输入根节点必须是对象")
    kind = data.get("data_kind")
    if kind not in ("live", "demo"):
        raise ValueError("data_kind 必须是 live 或 demo")
    store = text_value(data.get("store"), "store")
    if data.get("mode") != "pickup":
        raise ValueError("本版只支持 pickup 到店取餐")
    budget = integer(data.get("budget_cents"), "budget_cents")
    rules = constraints(data)
    integer(max_age_minutes, "max_age_minutes", 1)
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 6:
        raise ValueError("candidates 需要 1–6 份候选")
    now = now or datetime.now(timezone.utc)
    accepted, excluded, seen_ids = [], [], set()
    for position, candidate in enumerate(candidates, 1):
        label = f"候选 {position}"
        try:
            if not isinstance(candidate, dict):
                raise ValueError("候选必须是对象")
            label = text_value(candidate.get("id"), "id")
            if label in seen_ids:
                raise ValueError("候选 id 重复")
            seen_ids.add(label)
            title = text_value(candidate.get("title"), "title")
            items = meal_items(candidate.get("items"))
            conditions = strings(candidate.get("conditions", []), "conditions")
            check_preferences(items, rules)
            quote = candidate.get("quote")
            if not isinstance(quote, dict):
                raise ValueError("缺少官方核价整理结果")
            if quote.get("status") == "error":
                raise ValueError(text_value(quote.get("reason"), "quote.reason"))
            if quote.get("status") != "ok" or quote.get("tool") != "calculate-price":
                raise ValueError("需要成功的 calculate-price 核价")
            if quote.get("store") != store or quote.get("mode") != "pickup":
                raise ValueError("核价门店或取餐方式与当前需求不一致")
            if quote.get("currency") != "CNY":
                raise ValueError("仅支持人民币 CNY")
            source_ref = text_value(quote.get("source_ref"), "source_ref")
            text_value(quote.get("amount_field"), "amount_field")
            payable = integer(quote.get("payable_cents"), "payable_cents")
            if payable != amount_cents(quote.get("source_amount"), quote.get("source_unit")):
                raise ValueError("原金额与 payable_cents 不一致")
            timestamp = time_value(quote.get("quoted_at"))
            age = (now - timestamp).total_seconds()
            if kind == "live" and age < -60:
                raise ValueError("核价时间在未来，请检查时钟")
            if kind == "live" and not historical and age > max_age_minutes * 60:
                raise ValueError("核价时间已超过本地比较期限，请重新核价")
            accepted.append({"id": label, "title": title, "items": items,
                             "conditions": conditions, "payable_cents": payable,
                             "remaining_cents": budget - payable,
                             "quoted_at": quote["quoted_at"], "source_ref": source_ref})
        except ValueError as exc:
            excluded.append({"id": label, "reason": str(exc)})
    accepted.sort(key=lambda item: (item["payable_cents"], item["id"]))
    unique, baskets = [], set()
    for item in accepted:
        key = basket_key(item["items"])
        if key in baskets:
            excluded.append({"id": item["id"], "reason": "相同餐品及选项已有更低或相同核价"})
        else:
            baskets.add(key)
            unique.append(item)
    within = [item for item in unique if item["remaining_cents"] >= 0]
    over = [item for item in unique if item["remaining_cents"] < 0]
    return {"data_kind": kind, "store": store, "mode": "pickup", "budget_cents": budget,
            "recommended": within[:3], "over_budget": over[:3], "excluded": excluded,
            "differences": [basket_difference(a, b) for a, b in zip(unique, unique[1:])],
            "summary": {"submitted": len(candidates), "valid_distinct": len(unique),
                        "within_budget": len(within), "excluded": len(excluded)}}


def money(cents):
    return f"¥{Decimal(cents) / 100:.2f}"


def cell(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def markdown(result):
    label = "模拟示例 · 非实时售价" if result["data_kind"] == "demo" else "本轮官方核价整理结果"
    lines = [f"# 麦麦预算餐 · {label}", "",
             f"门店：{cell(result['store'])} · 到店取餐 · 预算：{money(result['budget_cents'])}", ""]
    if result["recommended"]:
        best = result["recommended"][0]
        lines.extend([f"本轮最低价：**{cell(best['title'])} · {money(best['payable_cents'])}**，"
                      f"预算剩余 {money(best['remaining_cents'])}。", ""])
    elif result["over_budget"]:
        closest = result["over_budget"][0]
        lines.extend([f"本轮有效餐单全部超预算；最接近的是 {cell(closest['title'])}，"
                      f"超出 {money(-closest['remaining_cents'])}。", ""])
    else:
        lines.extend(["本轮没有有效报价，请按下方原因处理后重新核价。", ""])
    groups = [("预算内餐单", result["recommended"]), ("超预算参考", result["over_budget"])]
    for heading, plans in groups:
        if not plans:
            if heading == "预算内餐单":
                lines.extend(["本轮没有可推荐的预算内餐单。", ""])
            continue
        lines.extend([f"## {heading}", "", "| 方案 | 餐品 | 应付 | 预算差额 | 优惠条件 | 核价时间 |",
                      "|---|---|---:|---|---|---|"])
        for plan in plans:
            items = "；".join(f"{item['name']} ×{item['quantity']}" for item in plan["items"] if not item["container"])
            remaining = plan["remaining_cents"]
            delta = ("剩余 " if remaining >= 0 else "超出 ") + money(abs(remaining))
            conditions = "；".join(plan["conditions"]) or "无额外条件记录"
            lines.append("| " + " | ".join(cell(value) for value in
                         (plan["title"], items, money(plan["payable_cents"]), delta, conditions, plan["quoted_at"])) + " |")
        lines.append("")
    if result["excluded"]:
        lines.extend(["## 未纳入比较", ""])
        lines.extend(f"- {cell(item['id'])}：{cell(item['reason'])}" for item in result["excluded"])
        lines.append("")
    if result.get("differences"):
        lines.extend(["## 差价与餐品变化", ""])
        for difference in result["differences"]:
            changes = []
            for field, label in (("added", "增加"), ("removed", "减少"), ("unchanged", "保持")):
                if difference[field]:
                    changes.append(label + "：" + "；".join(f"{cell(item['name'])} ×{item['quantity']}" for item in difference[field]))
            if difference["conditions_changed"]:
                changes.append("优惠条件不同，请同时核对各餐单条件")
            lines.append(f"- {cell(difference['from_title'])} → {cell(difference['to_title'])}："
                         f"总价相差 {money(difference['delta_cents'])}；" + "。".join(changes) + "。")
        lines.extend(["", "差价是两份完整餐单的总价差，不是新增餐品的单独售价。", ""])
    if result.get("warnings"):
        lines.extend(["## 本地导出提示", ""])
        lines.extend("- " + cell(warning) for warning in result["warnings"])
        lines.append("")
    lines.append("比较范围为本轮候选；餐品、价格和可售状态以麦当劳官方结算结果为准。")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="比较麦麦预算餐的本地核价数据（不联网）")
    parser.add_argument("input", type=Path, help="本地 JSON 文件")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--max-age-minutes", type=int, default=15, help="真实核价的本地比较期限，默认15分钟")
    args = parser.parse_args()
    try:
        if args.max_age_minutes < 1:
            raise ValueError("比较期限必须大于零")
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        result = compare(data, args.max_age_minutes)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print(f"无法比较：{exc}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
