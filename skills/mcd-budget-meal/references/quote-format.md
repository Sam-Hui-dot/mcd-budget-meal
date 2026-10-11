# 本地餐单格式

此格式用于整理 MCP 结果并交给比较脚本，**不是官方工具的请求或响应 schema**。官方文档没有列出完整参数，调用时读取连接器实际 schema。

顶层字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `data_kind` | `demo` / `live` | 示例或真实调用整理结果 |
| `store` | 字符串 | 所选门店名称或公开门店代码 |
| `mode` | `pickup` | 本版只比较同一门店到店取餐 |
| `budget_cents` | 非负整数 | 预算，人民币分 |
| `required_codes` | 字符串数组 | 必选餐品的实际编码，空数组表示不限制 |
| `candidates` | 数组，1–6项 | 本轮候选，常规只需最多三项；容许少量失败和替换记录 |

每份候选包含 `id`、`title`、`items`、`quote`；可选 `conditions` 为优惠或会员条件字符串数组。

每个 item 包含 `code`、`name`、正整数 `quantity`，可选 `option_key` 表示已选择的规格/替换组合。套餐需列出所选组成，以便检查必选项；父套餐加 `container: true`，用于展示、避免与组成重复算作餐品。组成的数量填整单实际份数，例如两份套餐各含一个汉堡，组成里的汉堡数量填2。必选编码使用具体餐品编码，而非父套餐编码。脚本只比较整单总价，不累加餐品价格。

成功 quote：

```json
{
  "status": "ok",
  "tool": "calculate-price",
  "source_ref": "本机工具返回消息的引用或脱敏证据编号",
  "amount_field": "本次工具响应里应付总价字段的真实路径",
  "source_amount": "25.90",
  "source_unit": "yuan",
  "currency": "CNY",
  "payable_cents": 2590,
  "quoted_at": "2026-10-11T16:00:00+08:00",
  "store": "所选门店",
  "mode": "pickup"
}
```

- `source_amount` 保留原值；`source_unit` 只能是 `yuan` 或 `cent`。单位必须根据实际工具说明/返回确认，无法确认时标成失败，不能猜。
- `payable_cents` 为精确转换的整数分；脚本校验它与原金额一致，不接受无法精确转换到分的金额。
- 必须使用整单应付总额，不能用商品原价、优惠金额或单品加购价填充。
- `quoted_at` 使用带时区的实际核价时间。`live` 默认超过15分钟归为待重新核价，这是本项目的比较策略，不代表官方报价有效期。
- `source_ref` 和 `amount_field` 便于人核对数据来源；脚本校验格式和金额一致性，不验证工具调用真实性。
- 原始工具返回只保存在本机 `private/`，公开示例不要保留手机号、定位、账户、优惠券实例编码、订单信息和凭证。

失败 quote：`{"status":"error","reason":"工具返回的脱敏错误原因"}`。不带价格、不替换成示例价格。

## 脚本

在仓库根目录运行（Python 3.10及以上，零第三方依赖）：

```powershell
python skills/mcd-budget-meal/scripts/compare_meals.py examples/demo-quotes.json
python skills/mcd-budget-meal/scripts/compare_meals.py private/live-quotes.json --format json
```

输出 Markdown 或 JSON 到标准输出。脚本不联网、不读取 Token、不发订单。示例模式始终标注“模拟示例”，其历史时间不会触发真实报价的新鲜度过滤。
