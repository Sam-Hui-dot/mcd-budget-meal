# WorkBuddy 开发记录

2026年10月11日，麦麦预算餐 v0.2.1。WorkBuddy 在已有项目上完成代码审查、两项修复和离线测试。下面保留两轮任务的输入及回复节选。

## 第一轮：检查现有项目

### 用户输入

```text
请审查当前工作空间的“麦麦预算餐”项目，分析有哪些值得做的优化。

读取 README.md、MCP_INTEGRATION.md、CHANGELOG.md、skills/mcd-budget-meal/SKILL.md、该技能的 scripts 和 references，以及 tests、docs、install.ps1。

先只读分析，不修改文件、不运行测试、不调用 MCP，不读取 Token、private 或 .workbuddy 配置，不提交或推送。

重点检查：
1. 预算、金额、餐品份数、偏好排除、去重和异常处理是否正确。
2. 安装与使用流程是否方便。
3. 文档描述是否符合实际代码能力。

请给出有具体代码依据的优化建议，区分确定的问题和可选增强，说明用户收益、改动成本和验证方法。优先推荐小而有用的改进，不为了凑数量提出建议。

项目已有开发成果，你本次参与代码审查和后续优化。先输出分析，等我决定是否实施。
```

### WorkBuddy 回复节选

以下摘录原审查表中随后实施的第3、4项，保留问题和代码依据两列。

| 原编号 | 问题 | 代码依据 |
|---|---|---|
| 3 | 批量计划校验失败时不报是哪一份候选 | `quote_meals.py:130-131` 直接调 `bind_items` / `check_preferences`，抛出的只有"展示餐单的编码、组成或数量与核价请求不一致""必选餐品 X 至少 2 份"；三份候选里哪一份出错、哪个编码不一致都不知道，且**整轮请求一条都发不出去** |
| 4 | 安装后 `private/` 落盘位置与文档不符 | `quote_meals.py:16-18`：装在 `~/.workbuddy/skills/mcd-budget-meal/scripts` 时 `parents[2]` = `~/.workbuddy`，命中 `skills/mcd-budget-meal` 存在 → `PROJECT_ROOT = ~/.workbuddy`，记录写进 `~/.workbuddy/private/`；而 `meal-plan.md:44` 写"技能单独安装时，只允许写到该技能自己的 private/" |

表中行号对应修复前的代码。原审查还提出认证错误提示、安装脚本残留等建议，本轮选择先解决这两项。

## 第二轮：修复并运行离线测试

### 用户输入

```text
先实施你报告中的第3和第4项：
1. 候选校验失败时显示候选id，保留具体错误原因。
2. 修正单独安装后的private记录目录，同时保留仓库内运行的现有路径规则。
允许修改相关代码、增加并运行纯离线测试。使用合成数据和临时目录，不联网、不读取Token或已有私人记录、不实际安装，不提交或推送。
保留金额、数量、偏好和失败停止规则。完成后汇报修改文件、实际测试命令和结果，再根据本任务真实对话更新workbuddy.md，保留已有记录，如实说明你的参与范围。
```

### WorkBuddy 完成回复节选

> 第 3、4 项已实施并验证完毕，未联网、未读 Token/私人记录、未安装、未提交推送。

**`skills/mcd-budget-meal/scripts/quote_meals.py` — 两项修复**

- `prepare_plan()`：把逐份校验（门店/取餐参数、`bind_items`、`check_preferences`、`conditions`、券编码）整体包进 `try`，捕获 `ValueError` 后重抛 `f"候选 {label}：{exc}"`。**原原因完整保留，失败规则未变**——仍是本地拒绝整份计划、一条核价请求都不发。
- 新增 `project_root(script_root=None)` 替换原来恒为 `parents[2]` 的算法：仓库副本（存在 `README.md` + `skills/mcd-budget-meal/SKILL.md`）返回仓库根，**保留原 `private/` 规则**；装在技能目录时返回技能自身目录，记录写进技能自己的 `private/`。`PROJECT_ROOT = project_root()`。金额、份数、偏好、失败停止逻辑一行未动。

**`tests/test_budget_meal.py` — 新增测试**

新增 `PlanDiagnostics` 5 项：绑定错误含候选 id；偏好错误含 id 且保留"至少 2 份，实际 1 份"；三份中第二份出错时只报 `second`；合成安装树记录目录落在技能内且越界被拒；合成仓库树保持仓库根且越界被拒。全部用 `tempfile` + `unittest.mock.patch`，不碰真实 `~/.workbuddy`。

**实际执行的命令与结果**

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests -v` | **Ran 27 tests … OK**（22 项历史 + 5 项新增，Python 3.13.12） |
| `quote_meals.py examples/plan-template.json --check-plan` | 通过，输出"未核价、未读取凭证、未联网" |
| `compare_meals.py examples/demo-quotes.json` | 与 README 一致：¥23.00 剩余 ¥7.00 / ¥28.50 剩余 ¥1.50 / ¥32.50 超出 ¥2.50 |
| 错误信息实测 | `候选 basic：必选餐品 DEMO-BURGER 至少 2 份，实际 1 份` |

上表是 WorkBuddy 当轮汇报的命令及结果。两个脚本的仓库相对路径均为 `skills/mcd-budget-meal/scripts/`。22项历史用例来自此前版本，5项新增用例由 WorkBuddy 本轮编写；本轮没有重新进行真实 MCP 联调或实际安装。

## 对应代码

两项修复、测试及相关文档更新已提交至 [366734a](https://github.com/Sam-Hui-dot/mcd-budget-meal/commit/366734abe325e256cedc2ed02cebe04c715525a5)。
