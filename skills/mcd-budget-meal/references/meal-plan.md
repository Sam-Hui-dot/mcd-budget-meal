# 餐单计划与批量核价

## 谁来准备计划

AI根据用户当前需求和真实门店数据构造计划；用户只提供预算、门店和偏好。脚本不猜菜单、不自动挑选套餐、不穷举商品。计划包含每份餐单的实际组成和完整官方核价参数，不填价格。

`examples/plan-template.json`展示结构，所有编码均虚构，`data_kind: demo`禁止联网。实际计划写入 `private/meal-plan.json`，标为 `data_kind: live`；这个标记必须对应当前真实菜单和已核实的选项，不能仅修改示例标记就发送。

## 顶层字段

- `data_kind`：真实计划为 `live`；模板为 `demo`。
- `store`：实际门店编码，与每份 `arguments.storeCode`完全相同。
- `mode`：本入口为 `pickup`，现在到店取餐。
- `budget_cents`：整数分，不允许小数或负数。
- `required_codes`：每个指定实际餐品至少一份，兼容旧格式。
- `required_quantities`：例如 `{ "实际汉堡编码": 2 }`。
- `required_groups`：可替代编码组，例如汉堡组、饮料组，字段为 `name`、`codes`、`minimum`。编码必须由当前菜单与套餐详情确认，不按名称臆测类别。
- `excluded_codes`：明确不要的实际餐品编码。
- `excluded_terms`：实际组成名称的文字匹配；例如“可乐”也会排除“无糖可乐”。需要只排除某一规格时使用具体编码。
- `candidates`：1–3份。每份含唯一 `id`、`title`、`items`、`conditions`、`arguments`。

`items`按报价格式列出实际组成。父套餐用 `container: true`，不计入必选数量。脚本检查这些编码与份数是否和 `arguments.items`及套餐 `roundList`完全一致，并从实际特调参数生成选项标识。

`arguments`必须按官方当前工具 schema构造。脚本进行类型、必填和枚举的基本检查，最终参数有效性以官方接口为准；它不是完整 JSON Schema验证器。核价前还会确认当前 `outputSchema.data.price`明确以分计价。

## 套餐和优惠券

- 套餐必须提供完整的 `roundList`和每轮实际子项，不能只列父套餐编码。
- 本批量入口暂限制每个套餐父项 `quantity=1`，多份父套餐的子项数量语义尚未做真实验证；独立单品支持多份。
- 同一轮全部餐单为同一门店、现在到店取餐。不接受外送、预约、团餐或随单购会员参数。
- 券来自该用户该门店的当前可用券；使用时提供真实 `couponId`、`couponCode`，并写明适用条件。不公开这些实例编码。
- 特调必须包含当前详情要求的 selectedKey / unselectedKey，脚本保留原参数，不自行补造。

## 命令

```powershell
# 本地结构与偏好检查，不加载认证、不联网
python skills/mcd-budget-meal/scripts/quote_meals.py examples/plan-template.json --check-plan

# 真实计划：一次完成核价与比较
python skills/mcd-budget-meal/scripts/quote_meals.py private/meal-plan.json --use-workbuddy-config --records-dir private/run-001
```

每一轮使用新的空记录目录，避免覆盖旧证据。记录目录按脚本所在位置确定：从仓库副本运行时写到仓库 `private/`；技能单独安装在 `~/.workbuddy/skills/mcd-budget-meal` 之类的技能目录时，写到该技能自己的 `private/`，不会写到技能目录之外。不指定记录目录也可以比较，但仅有请求摘要，没有落盘的原始返回，不应把摘要当作服务端调用凭证。设置环境变量 `MCD_MCP_TOKEN`时可省略 `--use-workbuddy-config`。

指定记录目录后，还自动生成 `comparison.json` 和可独立打开的 `meal-report.html`。后者只提取成功餐单的展示字段，不嵌入原始请求、认证、券实例编码或本机记录路径。失败候选只显示未纳入数量，具体原因看本机JSON。报告可调预算并比较差价，超过本地15分钟期限后提示重新核价；不请求网络。[完整报告说明](../../../docs/report-guide.md)

WorkBuddy连接器按官方地址匹配，不要求固定名称；多个连接器匹配时，加 `--server-key 你的连接器键名`。

## 失败规则与输出

1. 本地计划有冲突或组成不一致：整个计划拒绝，在认证和业务调用前修正；错误信息标明是哪一份候选（`候选 <id>：<原因>`），便于只改那一份。
2. schema或金额单位改变：在核价前停止。
3. 核价失败、连接中断或返回无法解释：停止后续候选，保留本轮此前已成功的结果；不重试。
4. 价格缺失、不是有限非负金额、回显商品不一致：不生成零元或猜测价格。
5. 比较时过期、缺少必选数量或含排除项：归入未纳入比较。

退出码：`0`完成且有有效报价（也可能全部超预算）；`1`有核价失败或无有效报价；`2`计划、schema、初始化或本地处理失败。模板检查通过退出0，但没有价格。

输出只有已归一化的餐单、金额、条件、时间和引用，不包含完整请求、券实例编码或认证请求头。原始返回仍可能有账户信息，因此仅存本机 `private/`，分享前应人工脱敏。
