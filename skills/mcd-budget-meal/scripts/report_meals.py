"""Render a standalone, offline report from validated comparison results."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from compare_meals import compare, integer, meal_items, strings, text_value, time_value

TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "report-template.html"
MARKER = "__MEAL_REPORT_DATA__"


def safe_integer(value, field):
    value = integer(value, field)
    if value > 9_007_199_254_740_991:
        raise ValueError(field + "超出浏览器安全整数范围")
    return value


def report_data(result, now=None, *, historical=False):
    """Explicit display-field allowlist: no requests, references, coupons or headers."""
    if result.get("data_kind") not in ("live", "demo") or result.get("mode") != "pickup":
        raise ValueError("报告需要live/demo到店取餐比较结果")
    meals = []
    for position, plan in enumerate(result["recommended"] + result["over_budget"], 1):
        visible = []
        for item in meal_items(plan["items"]):
            if item["container"]:
                continue
            identity = json.dumps([item["code"], item["option_key"]], ensure_ascii=False)
            visible.append({"name": item["name"], "qty": safe_integer(item["quantity"], "份数"),
                            "key": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]})
        timestamp = time_value(plan["quoted_at"]).isoformat()
        price = safe_integer(plan["payable_cents"], "应付金额")
        meals.append({"id": str(position), "title": text_value(plan["title"], "餐单标题"), "variants": [{
            "id": "quoted", "label": "本轮已核价组合", "tagline": "更换餐品后需要重新核价",
            "payableCents": price, "sourceNote": "保存的历史比较结果" if historical else "模拟价格" if result["data_kind"] == "demo" else "本轮官方核价整理",
            "quotedAt": timestamp, "conditions": strings(plan["conditions"], "优惠条件"), "items": visible}]})
    return {"kind": result["data_kind"], "historical": historical, "store": text_value(result["store"], "门店"), "storeCode": "",
            "window": "各餐单时间见卡片", "couponNote": "优惠条件见各餐单", "mode": "到店取餐",
            "initialBudgetCents": safe_integer(result["budget_cents"], "预算"), "meals": meals,
            "generatedAt": (now or datetime.now(timezone.utc)).isoformat(),
            "excludedCount": len(result["excluded"])}


def snapshot_data(source):
    """Validate a public historical illustration; no inferred minute timestamps."""
    if source.get("kind") != "snapshot":
        raise ValueError("历史预览必须标注kind=snapshot")
    output = {key: text_value(source.get(key), key) for key in ("store", "storeCode", "window", "couponNote", "mode")}
    if output["mode"] != "到店取餐":
        raise ValueError("报告仅支持到店取餐")
    output.update({"kind": "snapshot", "initialBudgetCents": safe_integer(source.get("initialBudgetCents"), "预算"),
                   "excludedCount": 0, "meals": []})
    meals = source.get("meals")
    if not isinstance(meals, list) or not 1 <= len(meals) <= 6:
        raise ValueError("历史预览需要1–6份餐单")
    for index, meal in enumerate(meals, 1):
        variants = meal.get("variants")
        if not isinstance(variants, list) or not 1 <= len(variants) <= 6:
            raise ValueError("每份餐单需要1–6个已核价版本")
        clean = {"id": str(index), "title": text_value(meal.get("title"), "标题"), "variants": []}
        for number, variant in enumerate(variants, 1):
            rows = variant.get("items")
            if not isinstance(rows, list) or not rows:
                raise ValueError("餐单缺少实际组成")
            items = []
            for row in rows:
                name = text_value(row.get("name"), "餐品名")
                qty = safe_integer(row.get("qty"), "份数")
                if not qty:
                    raise ValueError("份数必须大于0")
                items.append({"name": name, "qty": qty, "key": name})
            clean["variants"].append({"id": str(number), "label": text_value(variant.get("label"), "版本"),
                "tagline": "当次已核价版本", "payableCents": safe_integer(variant.get("payableCents"), "应付"),
                "sourceNote": "历史核价快照", "quotedAt": output["window"],
                "conditions": strings(variant.get("conditions", []), "优惠条件"), "items": items})
        output["meals"].append(clean)
    return output


def render(data):
    # Escaping < also prevents an item name from closing the application/json tag.
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        serialized = serialized.replace(char, escaped)
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(MARKER) != 1:
        raise ValueError("报告模板标记缺失或重复")
    return template.replace(MARKER, serialized)


def html_report(result, now=None, *, historical=False):
    return render(report_data(result, now, historical=historical))


def restore_comparison(source, now=None):
    """Recheck saved display data; never redate it or contact the official service."""
    if not isinstance(source, dict):
        raise ValueError("保存的比较结果必须是JSON对象")
    candidates = []
    for key in ("recommended", "over_budget"):
        rows = source.get(key)
        if not isinstance(rows, list):
            raise ValueError("保存的比较结果缺少餐单数组：" + key)
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("保存的餐单必须是对象")
            price = safe_integer(row.get("payable_cents"), "应付金额")
            candidates.append({"id": row.get("id"), "title": row.get("title"),
                "items": row.get("items"), "conditions": row.get("conditions", []),
                "quote": {"status": "ok", "tool": "calculate-price", "store": source.get("store"),
                    "mode": source.get("mode"), "currency": "CNY", "source_amount": price,
                    "source_unit": "cent", "payable_cents": price, "quoted_at": row.get("quoted_at"),
                    "source_ref": "local-saved-comparison", "amount_field": "saved.payable_cents"}})
    if not 1 <= len(candidates) <= 6:
        raise ValueError("保存的比较结果需要1–6份有效餐单；空结果不能恢复为报价")
    restored = compare({"data_kind": source.get("data_kind"), "store": source.get("store"),
        "mode": source.get("mode"), "budget_cents": source.get("budget_cents"),
        "candidates": candidates}, now=now, historical=True)
    if restored["excluded"]:
        raise ValueError("保存的餐单未通过金额、时间、组成或唯一性检查，停止恢复")
    excluded = source.get("excluded", [])
    if not isinstance(excluded, list):
        raise ValueError("保存的excluded必须是数组")
    # Preserve only the count; raw reasons are not copied into the HTML.
    restored["excluded"] = [{} for _ in excluded]
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--snapshot", action="store_true", help="Render reviewed public historical display data")
    mode.add_argument("--from-comparison", action="store_true", help="Restore saved comparison.json as an explicitly historical report")
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if args.snapshot:
        output = args.output.resolve()
        page = render(snapshot_data(source))
    else:
        from quote_meals import private_path
        output = private_path(args.output)
        page = html_report(restore_comparison(source), historical=True) if args.from_comparison else html_report(compare(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a previous report or evidence file.
    with output.open("x", encoding="utf-8") as stream:
        stream.write(page)
    print("餐单报告已生成：" + str(output))


if __name__ == "__main__":
    main()
