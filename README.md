# 麦麦预算餐

“预算30元，想吃汉堡和喝的，帮我选几种。”

![30元预算的真实核价快照](assets/result-preview.svg)

麦麦预算餐是基于麦当劳中国 MCP 的点餐决策 Skill：查询所选门店菜单和可用优惠，将少量候选交给官方工具核价，给出预算内的餐单、剩余预算与优惠条件。适合想控制单餐预算、又不想反复切换菜单和优惠券页面的单人到店取餐用户。

## 能做什么

- 保留你想吃的餐品，比较最多三份不同搭配。
- 显示整单应付总额、预算余量、餐品数量与优惠条件。
- 换饮料或加小食后重新核价。
- 无预算内方案时明确列出超额，不擅自增加预算。
- 检查必选数量、不要的餐品和可替代的餐品类别，例如“至少两个汉堡”“饮料不要可乐”。
- 使用批量入口一次处理最多三份已准备的候选；官方核价返回自动进入预算比较，减少手工抄价格。

可以这样问：

| 需求 | 输出重点 |
|---|---|
| “30元，汉堡和饮料” | 最低价、另两份不同搭配、剩余预算 |
| “不要可乐，汉堡保留” | 检查排除项，替换后对完整餐单重新核价 |
| “25元，两个汉堡” | 实际汉堡份数达到2，超预算时明确说明 |
| “有券就比较，没有券也行” | 先核实门店可用券；没有券时正常比较 |

本版仅支持同一门店、单人到店取餐，停在餐单建议阶段。没有自动下单功能。

## 安装与使用

需要支持远程 MCP 的 AI 客户端，如 WorkBuddy、Cherry Studio 或 Cursor。客户端运行 Skill 与用它开发项目是两回事；使用本项目不要求 WorkBuddy。配套脚本需要 Python 3.10及以上，无第三方依赖。原生工具可正常调用时，脚本可选；遇到本次 WorkBuddy 核价兼容性问题时，使用直连脚本完成核价。

1. 从 [麦当劳 MCP 平台](https://open.mcd.cn/mcp) 登录并激活自己的 Token。
2. 按 [官方 MCP 指南](https://github.com/M-China/mcd-mcp-server#2-快速开始) 接入 `https://mcp.mcd.cn`，使用 Streamable HTTP。
3. 下载本仓库。客户端支持 Skill 导入时，导入完整的 `skills/mcd-budget-meal` 文件夹；否则打开仓库目录，要求 AI 读取 `skills/mcd-budget-meal/SKILL.md`，按其中流程处理本次请求。只粘贴正文也可使用对话流程，配套脚本需能访问本地文件。
4. 输入预算、门店、喜欢或不想要的餐品。AI 通过你的 MCP 连接器查询并核价，然后展示餐单。

**WorkBuddy用户的简便安装**：下载仓库 ZIP并解压，在仓库目录的 PowerShell 中运行 `./install.ps1`，然后新开 WorkBuddy 会话。脚本只复制技能文件，已有技能会先备份；它不安装软件、不读取 Token、不修改连接器。也可以把下面这句话发给自己的 WorkBuddy：

```text
请安装技能 https://github.com/Sam-Hui-dot/mcd-budget-meal 。
将 skills/mcd-budget-meal 整个文件夹放入用户技能目录，保留 scripts 和 references。
安装后告诉我实际目录，并提示我新开会话。已有麦当劳连接器，不要重配。
```

完整点击顺序和常见问题见 [快速开始](docs/quick-start.md)。

WorkBuddy 若报告 `/items: must be array`，Skill会改用项目内的官方 MCP直连路径。无需反复修改连接器或重新申请 Token，具体操作见[直连核价说明](skills/mcd-budget-meal/references/workbuddy-compatibility.md)。

公开配置示例在 [mcp-config.example.json](mcp-config.example.json)，只含 `${MCD_MCP_TOKEN}` 占位符。环境变量展开方式取决于客户端；若不支持，在客户端自己的私有连接器配置中填入 Token，不修改公开示例、不把 Token 发到聊天里。

首次使用可输入：

```text
请读取 skills/mcd-budget-meal/SKILL.md，使用已启用的麦当劳 MCP。
预算30元，一个人，现在到店取餐，想吃一个汉堡和一杯饮料。
先让我选门店，再比较最多三份真实核价的餐单。不下单。
```

然后可以追问：

```text
保留汉堡，把饮料换成菜单里可选的另一种，预算还是30元，请重新核价。
```

## 离线示例

想先看比较格式，可以运行：

```powershell
python skills/mcd-budget-meal/scripts/compare_meals.py examples/demo-quotes.json
```

**下面全部是模拟餐品与价格，不是实时菜单，也不是真实 MCP 调用记录。**

| 示例方案 | 内容 | 示例金额 | 相对30元预算 |
|---|---|---:|---:|
| 基础搭配 | 示例汉堡＋示例茶饮 | ¥23.00 | 剩余 ¥7.00 |
| 加小食搭配 | 示例汉堡＋示例小份薯条＋示例茶饮 | ¥28.50 | 剩余 ¥1.50 |
| 增加一份小食 | 在加小食搭配上增加示例小食 | ¥32.50 | 超出 ¥2.50 |

比较脚本接收 AI 整理的核价 JSON，不持有凭证、不调用网络。它检查金额单位、必选编码、门店一致性和时间，按整单应付金额排序并合并相同餐单。详见 [本地数据格式](skills/mcd-budget-meal/references/quote-format.md)。

真实数据可以保存在被 Git 忽略的 `private/live-quotes.json`，再运行：

```powershell
python skills/mcd-budget-meal/scripts/compare_meals.py private/live-quotes.json --format json
```

## MCP 流程

```text
预算与口味 → 选定门店 → 查菜单、门店可用券 → 核对套餐选项
          → 构造少量候选 → 官方整单核价 → 预算比较 → 餐单建议
```

主要工具：`query-nearby-stores`、`query-meals`、`query-store-coupons`、`query-meal-detail`、`calculate-price`。具体职责和接入状态见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 批量核价与自动比较

AI先查询当前真实菜单、套餐详情和券，再将完整候选写入 `private/meal-plan.json`。用户不需要手写编码或价格。在仓库目录运行：

```powershell
python skills/mcd-budget-meal/scripts/quote_meals.py private/meal-plan.json --use-workbuddy-config --records-dir private/run-001
```

脚本检查餐单组成与请求是否一致，读取当前官方工具定义确认金额单位，然后顺序核价最多三份候选。成功报价自动换算为整数分、检查偏好并生成比较表。第一次失败后停止剩余请求，不自动重试；已有有效结果仍可查看。详细格式见[餐单计划说明](skills/mcd-budget-meal/references/meal-plan.md)。

想先了解计划结构，可以做本地检查（不联网、不读取凭证）：

```powershell
python skills/mcd-budget-meal/scripts/quote_meals.py examples/plan-template.json --check-plan
```

这个模板全部使用虚构编码，标为 `demo`，脚本禁止将它发到官方服务。原始调用记录只可写入本项目 `private/`，公开展示请使用经过人工脱敏的摘要。

## 当前状态与边界

2026年10月11日在深圳南科大餐厅完成真实菜单、可用券和套餐详情查询，三份官方核价分别为 ¥14.90、¥22.90、¥26.90；比较脚本成功计算预算余量。大堡口福三件套将可乐换为无糖可乐后重新核价为 ¥22.90。见[本次真实运行](examples/verified-run.md)。

上述真实运行属于初版单工具直连路径。此次升级新增批量入口、偏好数量检查、安装脚本和离线回归用例；新入口的验证状态单独记录在 [版本说明](CHANGELOG.md)，不扩大原有真实运行记录的范围。`demo-quotes.json` 始终是模拟数据。

比较只覆盖本轮候选；它不保证全菜单最低价。价格、券适用性和供应状态以麦当劳官方当前结果为准。营养、配料及过敏原未纳入本版推荐规则。

## 项目结构

```text
skills/mcd-budget-meal/
  SKILL.md                 对话流程、门店和候选选择
  scripts/mcp_query.py     官方 MCP查询客户端
  scripts/quote_meals.py   批量核价、请求绑定、自动比较
  scripts/compare_meals.py 预算与偏好检查、排序、Markdown输出
  references/             数据格式和兼容说明
examples/                 虚构示例与历史真实运行摘要
tests/                    纯离线回归用例，无Token、无网络
install.ps1               Windows用户级技能安装
```

离线回归命令为 `python -m unittest discover -s tests -v`，检查金额、数量、排除项、过期报价、异常响应和失败停止行为。它使用合成响应，不代表真实 MCP 联调结果。

## 许可与声明

本项目原创 Skill、脚本和示例采用 [MIT License](LICENSE)。官方参赛声明保留原文，适用其原有声明和规则；本项目非麦当劳官方产品。使用 MCP 须遵守官方服务规则。
