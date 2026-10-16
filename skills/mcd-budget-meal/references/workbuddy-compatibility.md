# WorkBuddy 核价兼容性：使用已验证的直连路径

2026年10月11日，WorkBuddy 的延迟工具入口报告 `/items: must be array`。设置工具级 `defer_loading: false` 后，该次运行仍走延迟入口。因此无需反复改配置或重启。

随后将同一份餐单参数直接发到官方 MCP，核价成功返回2690分。项目已增加零依赖的 `scripts/mcp_query.py`；三份餐单核价、预算比较与一次饮料替换核价均成功，保留原版功能。

## 用法

新版本推荐让 AI根据已查询的真实菜单准备 `private/meal-plan.json`，再运行：

```powershell
python skills/mcd-budget-meal/scripts/quote_meals.py private/meal-plan.json --use-workbuddy-config --records-dir private/run-001
```

这一入口顺序核价最多三份候选、自动转换整单金额并生成比较表。首次失败即停止后续请求，不经过 WorkBuddy延迟工具入口。格式见 [meal-plan.md](meal-plan.md)。下方单工具命令仍可用于查菜单、详情和单次诊断。

前提：Python 3.10及以上；用户已授权使用自己的麦当劳连接器查询和核价。脚本固定访问 `https://mcp.mcd.cn`，仅允许五个查询或核价工具，不下单、不领券、不支付，不修改连接器。

默认从 `MCD_MCP_TOKEN` 环境变量取得认证。本机已配置 WorkBuddy 的用户可以显式使用 `--use-workbuddy-config`，读取 `~/.workbuddy/mcp.json` 中现有的 mcd-mcp 认证。凭证不传入命令行、不打印、不保存到响应文件。

2026年10月16日起按官方地址匹配连接器，键名不要求为 `mcd-mcp`；匹配多个连接器时使用 `--server-key`选择。批量入口已完成三份真实核价及换饮料重新核价，并自动生成餐单报告，见[本轮记录](../../../examples/verified-run-2026-10-16.md)。

在仓库根目录获取当前核价 schema：

```powershell
python skills/mcd-budget-meal/scripts/mcp_query.py calculate-price --describe --use-workbuddy-config
```

将按当前菜单和套餐详情生成的真实请求写入 `private/quote-request.json`，再核价：

```powershell
python skills/mcd-budget-meal/scripts/mcp_query.py calculate-price --args private/quote-request.json --output private/quote-response.json --use-workbuddy-config
```

命令一次只调用选定工具，不自动重试。结果 JSON 输出到标准输出，`--output` 保存请求与原始响应，认证请求头不写入文件。先调用一份，成功后再完成其余候选。失败则停止，保留错误，不用空数组、缺字段或字符串化数组试探。

其他可用工具：`query-nearby-stores`、`query-meals`、`query-store-coupons`、`query-meal-detail`。同样通过 `--describe` 获取实时 schema，`--args` 提供真实参数。位置查询只能使用用户给出的位置。

本次成功响应应付总额为 `result.structuredContent.data.price`，单位分；据真实 schema 与响应转换，不累加菜单参考价。整理报价时引用保存记录并交给 `compare_meals.py`。

## 单份套餐参数形状

- 顶层：`storeCode` 字符串、`orderType: 1`、`beType: 1`；到店取餐不传 `beCode`。
- `items` 为非空数组，每项 `productCode` 字符串、`quantity` 为正整数。
- `roundList` 为对象数组，每项含字符串 `round` 和数组 `comboItemList`。
- 每个套餐子项含当前详情返回的 `code` 和整数 `quantity`。
- 特调按当前 schema 与详情的 selectedKey / unselectedKey 规则组织，不能猜测编码。
- `query-meal-detail` 查询商品使用 `code` 字段；核价商品使用 `productCode` 字段。

## 故障证据与范围

本机 WorkBuddy 的 `DeferExecuteTool.validateParams` 生成原始错误，在其调用流程中位于 `executeMcpTool` 之前。直接调用官方 MCP 可接受该份相同数组请求，说明此次餐单参数可以被官方服务处理。WorkBuddy 中具体在哪一步改变了参数或 schema，尚未取得足够内部数据确定。

直接加载选项有腾讯文档依据，但在此次 WorkBuddy 运行中未生效。`mcp-config.workbuddy.example.json` 仅保留此前尝试的配置，不是本次已验证解决路径；不建议用户重复该试验。

来源：
- 官方 MCP 接入：https://github.com/M-China/mcd-mcp-server
- MCP Streamable HTTP：https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- 腾讯延迟加载说明：https://cloud.tencent.com/document/product/1831/137039
