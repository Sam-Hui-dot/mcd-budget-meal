# WorkBuddy 参与记录

本记录覆盖两轮实际参与：第一轮代码审查和方案分析，第二轮候选错误定位、单独安装记录目录两项修复，以及27项离线回归。开发基线为`35680a3`，第二轮形成的本地版本为v0.2.1。

以下按各阶段原始时点保留上下文；第一轮中的“未实施”“未运行测试”等说明仅描述当时状态，第二轮的实际成果见文末。文件内容记录开发参与，不代表已获得赛事奖励。

## 第一轮审查阶段的范围（当时记录）

记录整理日期：2026年10月11日。项目：麦麦预算餐，现有版本`35680a3`。

本项目此前的Skill、脚本与材料主要在Codex协作中完成。WorkBuddy本次参与现有项目的代码审查和优化方案分析，不将此前开发或历史22项测试归为本次WorkBuddy完成。

本文件中的WorkBuddy回复由用户从实际任务中提供，以下保留该回复原文。记录整理者没有直接操作该WorkBuddy任务。本次回复明确说明未改文件、未运行测试/脚本、未调用MCP、未读取私人目录或凭据配置；目前只记录审查参与，没有新增实施或测试成果。

用户已确认下列提示词原样发送给WorkBuddy。本节保留的是用户确认实际发送的输入。

## 用户实际输入

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

## WorkBuddy 原始回复（用户提供）

```markdown
I'll start by reading the project files to understand the codebase.
Now let me read the skill definition and its scripts.
Let me check a few structural details (git ignore rules, config examples, Python syntax compatibility).
已完成只读审查（未改文件、未运行测试/脚本、未调用 MCP、未读 `private/` 与任何凭据配置）。

## 结论先看

**核心决策逻辑没有发现会算错钱/算错份数的缺陷。** 金额换算、必选数量、排除项、去重、时效、失败停止这几条我逐行核过，行为与文档一致：

- `compare_meals.py:31-45` 强校验单位、拒绝负值与无法精确到分的小数；`:186` 要求 `payable_cents` 与原始金额一致（缺失即排除，不会变零元）。
- `container` 父套餐不计入份数（`:122`、`:87`），去重键 `(code, option_key)` 让"换无糖可乐"成为不同餐单（`:83-90` + `quote_meals.py:95-96`）。
- 排除项对容器也生效（`:129`），冲突必选/排除整份拒绝（`:103`），全部超预算时"最接近"= 应付最低 = 超额最小（`:200`+`:210`）。
- 文档自洽：README 的 ¥23.00 / ¥28.50 / 超出 ¥2.50 与 `demo-quotes.json` 一致；CHANGELOG 的"22 项用例"实际为 13+9=22；`private/` 已被 `.gitignore` 忽略（不是泄漏风险）。

值得做的改动集中在**错误可诊断性**和**文档/代码一致性**，下面按"确定的问题 / 可选增强"分开。

## 一、确定的问题

| # | 问题 | 代码依据 | 用户收益 | 成本 | 验证办法 |
|---|---|---|---|---|---|
| 1 | 直连认证读取僵化，失败信息不可操作 | `mcp_query.py:26-28` 硬编码 `config["mcpServers"]["mcd-mcp"]`；键名不同 → `KeyError`，文件缺失 → `FileNotFoundError`，二者都退化成 `:162` 的 "Check local args/config and network" | WorkBuddy 用户（install.ps1 主要受众）首次失败时能直接知道"没配连接器 / 服务器键名不是 mcd-mcp / Token 还是 `${...}` 占位符"，而不是原地打转 | 小，约 15 行：可选 `--server-key`，或按 `url == ENDPOINT` 自动匹配；三类失败分别给中文提示（只列键名，不打印 Token） | 新增离线用例：在临时目录造一个假 `mcp.json`（monkeypatch `Path.home`，不碰真实配置），断言三种分支的报错文案 |
| 2 | SKILL 承诺的 401/429 区分没有落地 | `SKILL.md:28` 写"401 提示用户检查本机连接器；429 停止本轮调用"；但 `mcp_query.rpc` 用 urllib，HTTPError 直接冒泡，`quote_meals.py:251-255` 只判断 `ValueError`，401/429 都变成同一句泛化提示 | Token 过期/未激活是最常见失败，能立刻区分"认证问题"与"网络/参数问题"，避免无效重试 | 小，约 5-8 行：在 `run` 的 `except` 里看 `getattr(exc, "code", None)`，401/403→认证提示，429→限流停止 | 构造带 `code` 的 `urllib.error.HTTPError` 喂给 `run`，断言 reason 含"认证"/"限流" |
| 3 | 批量计划校验失败时不报是哪一份候选 | `quote_meals.py:130-131` 直接调 `bind_items` / `check_preferences`，抛出的只有"展示餐单的编码、组成或数量与核价请求不一致""必选餐品 X 至少 2 份"；三份候选里哪一份出错、哪个编码不一致都不知道，且**整轮请求一条都发不出去** | AI 能一次定位并修正，少一轮真实的反复构造 | 极小，3-5 行：循环内包一层 `try/except ValueError`，重抛时加 `候选 {label}：` 前缀 | 单测 `assertRaisesRegex` 断言消息含候选 id |
| 4 | 安装后 `private/` 落盘位置与文档不符 | `quote_meals.py:16-18`：装在 `~/.workbuddy/skills/mcd-budget-meal/scripts` 时 `parents[2]` = `~/.workbuddy`，命中 `skills/mcd-budget-meal` 存在 → `PROJECT_ROOT = ~/.workbuddy`，记录写进 `~/.workbuddy/private/`；而 `meal-plan.md:44` 写"技能单独安装时，只允许写到该技能自己的 private/" | 原始记录落在技能目录内，用户找得到、删得掉，与文档一致（`:249` 的 `source_ref` 相对路径也跟着变准） | 小，1-3 行，但要保留仓库内"仓库根 private/"的现有行为，建议把 `PROJECT_ROOT` 计算抽成函数以便测试 | 用 tmp 目录造两种布局（仓库 / 用户技能目录）断言解析结果 |
| 5 | 安装脚本重装残留旧文件 | `install.ps1:33-35` 用 `Copy-Item -Recurse -Force` 合并进已有目录，旧版本遗留文件不会被删除；另外从工作副本（含 `scripts/__pycache__`，虽未被 git 跟踪、ZIP 不受影响）安装会把 `.pyc` 一起装上 | 升级后不会出现"脚本已删但仍在"的诡异行为 | 极小：备份后先删目标目录再复制 + `-Exclude '__pycache__'` | PowerShell 语法检查 + 在临时 HOME 目录实装一次比对文件清单 |

## 二、可选增强（收益较小或需权衡）

- **候选级偏好失败只排除该份，不整轮拒绝**：现在 `prepare_plan` 里任一份不满足偏好就全盘报错，而手动路径 `compare_meals.compare` 是逐份排除的，两种入口行为不同。改成"标记排除其余照常核价"能少浪费一轮，但会削弱现有的 fail-fast 语义（本地问题不消耗真实调用），需要你定夺，不建议默认改。
- **安装后的自检命令与回滚说明**：`docs/quick-start.md` 只给仓库根目录命令，装着技能的用户不知道该跑 `python ~/.workbuddy/skills/mcd-budget-meal/scripts/quote_meals.py examples/plan-template.json --check-plan`；也没写怎么用 `~/.workbuddy/skill-backups/` 回滚。纯文档，几行。
- **`quote_meals.py` 的本地文件错误被泛化**：`main` 的兜底（`:287-290`）把 OSError 也压成"检查本机计划、配置或网络"，计划文件不存在时看不出是路径问题。可只对 OSError 放行路径信息（仍不打印请求内容）。
- **Markdown 输出不带 `source_ref`**：比较表有核价时间但没有证据引用，人工核对时要回头翻 `private/`。可在表下加一行脚注，成本很低。

## 三、最推荐的一项

**先做 #3（候选 id 前缀），再顺手做 #1（认证读取 + 错误信息）。** #3 是三行改动、零风险、直接减少无效真实调用；#1 是对外分发时最可能卡住新用户的那道坎，两者都不动金额与偏好逻辑，回归用例只需各加一条断言。

补充两点上下文：仓库根目录还没有 `workbuddy.md`（`docs/workbuddy-review-task.md` 目前是未跟踪文件），参赛材料需要时再按该文档第四步整理；另外仓库无 `AGENTS.md`，无需遵循额外约定。

要我实施哪一项，或者要我先把某项改成可离线验证的补丁？
```

## 第一轮结束时的静态核对与待办

Codex对上述建议做了静态核对：候选错误缺少标识、单独安装时根目录误判、泛化错误提示、安装时合并残留等问题有代码依据。认证自动选择和安装目录删除需进一步约束，不能直接照建议进行。

特别说明：HTTP认证失败也可能发生在初始化阶段，仅修改核价循环的异常分支不能完整解决；安装脚本使用`GetFolderPath(UserProfile)`，仅改变HOME不能保证隔离安装目标；用户在对话中提供的全局AGENTS指令仍适用，即使仓库内无该文件。原回复关于`.gitignore`和“零风险”的判断也不作为无条件保证。

当前尚未由WorkBuddy实施上述建议，也没有本次WorkBuddy新增测试结果。拟优先处理候选错误定位及单独安装的记录根目录，待用户选择并在WorkBuddy中执行后再追加真实记录。

本文件仍是待完善的参与记录，尚未推送。奖励资格以活动官方审核与排名为准。

---

## 第二轮：实施阶段（同一工作空间内继续执行）

上一节的审查输出即本会话上一轮回复；以下第二轮由 WorkBuddy 在同一工作空间内直接读取文件、修改代码、新增并运行离线用例后落盘，不是转述。用户选择实施第 3、4 项。

### 用户第二轮真实输入

```text
先实施你报告中的第3和第4项：
1. 候选校验失败时显示候选id，保留具体错误原因。
2. 修正单独安装后的private记录目录，同时保留仓库内运行的现有路径规则。
允许修改相关代码、增加并运行纯离线测试。使用合成数据和临时目录，不联网、不读取Token或已有私人记录、不实际安装，不提交或推送。
保留金额、数量、偏好和失败停止规则。完成后汇报修改文件、实际测试命令和结果，再根据本任务真实对话更新workbuddy.md，保留已有记录，如实说明你的参与范围。
```

### 实际改动

1. `skills/mcd-budget-meal/scripts/quote_meals.py` — `prepare_plan()` 内逐份校验（`arguments` 门店/取餐/禁用参数、`bind_items`、`check_preferences`、`conditions`、券编码检查）整体包进 `try`，捕获 `ValueError` 后重抛为 `f"候选 {label}：{exc}"`。保留原原因，保留"本地拒绝整份计划、不发出核价请求"的失败规则。实测消息：`候选 basic：必选餐品 DEMO-BURGER 至少 2 份，实际 1 份`。
2. `skills/mcd-budget-meal/scripts/quote_meals.py` — 新增 `project_root(script_root=None)`：仓库副本（`<repo>/skills/mcd-budget-meal/scripts` 且 `<repo>/README.md` 存在）返回仓库根，保持原有 `private/` 规则；安装在技能目录时返回技能自身目录，记录写入该技能自己的 `private/`。`PROJECT_ROOT = project_root()`，金额、份数、偏好与失败停止逻辑未改。
3. `tests/test_budget_meal.py` — 新增 `PlanDiagnostics` 类 5 项用例：绑定错误含候选 id；偏好错误含候选 id 且保留原因；第二份出错时只报 `second`；合成安装树记录目录落在技能内且越界目录被拒；合成仓库树保持仓库根规则且越界目录被拒。全部使用 `tempfile` 合成目录与 `unittest.mock.patch`，不触碰真实 `~/.workbuddy`。
4. `CHANGELOG.md` — 新增 v0.2.1 条目（修复内容、27 项回归、明确未真实联调/未安装验证/未提交）。
5. `skills/mcd-budget-meal/references/meal-plan.md` — 记录目录规则改为"按脚本位置确定"，失败规则补充 `候选 <id>：<原因>` 说明。

### 实际执行的命令与结果

```powershell
python -m unittest discover -s tests -v
# Ran 27 tests ... OK（22 项历史用例 + 5 项新增，全部通过；Python 3.13.12）

python skills/mcd-budget-meal/scripts/compare_meals.py examples/demo-quotes.json
# 基础搭配 ¥23.00 剩余 ¥7.00；加小食搭配 ¥28.50 剩余 ¥1.50；增加一份小食 ¥32.50 超出 ¥2.50

python skills/mcd-budget-meal/scripts/quote_meals.py examples/plan-template.json --check-plan
# {"data_kind":"demo","store":"DEMO-STORE","budget_cents":3000,"candidate_count":1,
#  "status":"本地计划检查通过；未核价、未读取凭证、未联网"}

# 记录目录解析与错误信息实测（合成临时目录，已清理）
# checkout PROJECT_ROOT  = C:\Users\Sam\Documents\Codex\2026-10-08\ai-david\mcd-budget-meal
# installed PROJECT_ROOT = <temp>\home\.workbuddy\skills\mcd-budget-meal
# error message          = 候选 basic：必选餐品 DEMO-BURGER 至少 2 份，实际 1 份
```

22 项历史用例为项目此前成果，本次由 WorkBuddy 一并运行通过；新增 5 项为本次编写。

### 本轮未执行、未验证

- 未调用麦当劳 MCP、未做真实核价联调；未运行 `install.ps1`、未做真实安装与渲染验收。
- 未读取 `private/`、Token 或 `~/.workbuddy/mcp.json`；未提交、未推送、未改动 Git 署名。
- 第 1、2、5 项（认证键名与错误信息、401/429 区分、安装脚本残留）仍为建议，未实施。上文"整理者核对"中关于认证自动选择与安装目录删除需额外约束的提醒依旧有效，本轮未触及这两处。

### 脱敏与范围

本轮测试目录为系统临时目录中的合成结构，运行后已清理；本文件不含 Token、账号凭证、优惠券实例编码、个人定位或 `private/` 原始响应。

WorkBuddy 本次参与范围是**代码审查、方案设计与两项小修复的实施及离线验证**，不是本项目原创开发者；初版与 v0.2 主体实现、真实核价运行及历史用例由参赛者使用其他工具完成。
