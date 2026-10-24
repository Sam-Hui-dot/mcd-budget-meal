# 麦麦预算餐视觉设计

2026-10-12–13。本轮由Codex设计，延续“先核价，再选餐”的产品定位。

## 设计方向

深咖色封面、暖黄色重点与原创餐食／预算小票插画；正文保留奶油色背景和清晰的餐单卡片。README增加封面、信息徽章、章节导航及完整历史案例效果图。预览页将预算输入与餐单比较放在视觉中心，压缩重复说明。

保留：名称、历史价格及组成、时间范围、预算输入与边界处理、饮料切换、三段复制回退、移动布局和离线单文件使用方式。

替换：封面、颜色与字体层级、卡片间距、长篇重复提示。核心Skill和Python核价逻辑不变。

## 资产

- `assets/meal-illustration-v3.png`：内置imagegen生成的原创透明底插画，不代表具体在售餐品。
- `assets/cover-layout-v3.svg`：代码排版的可编辑封面源文件。
- `assets/cover-v3.jpg`：封面源文件的浏览器导出图，用于GitHub README。
- `assets/meal-comparison-v3.svg`：使用脱敏历史核价记录的效果展示图，不公开门店与核价时段。
- `assets/badges/`：本地信息徽章。未设CI，因此不展示自动测试通过徽章。
- `docs/preview.html`：插画嵌入页面，可单文件离线打开。

## 插画生成提示词摘要

完整实际提示词保存在 [imagegen-prompt.txt](../assets/imagegen-prompt.txt)。

使用内置imagegen，透明背景。Premium playful 3D clay / paper-cut hybrid still life: sesame burger, red carton of fries, cream soda cup with red lid, curling blank thermal receipt, mustard coin disks and red checkmark paper token. Compact cohesive composition, warm soft studio light and tactile paper/clay texture. Palette: mustard #ffc72c, tomato #d0241c, cream #fff8e6, espresso accents. Original striped packaging; no corporate logo, golden arches, lettering, numbers or watermark. Receipt only blank ruled lines. Decorative illustration, not a photo of a specific menu item.

## 验收标准

价格与组成保持原记录；预算边界和饮料切换的13组离线场景通过；已有27项Python回归保持通过；通过现有Edge插件核对封面、桌面和375/320像素容器布局，页面无横向溢出。真实MCP联调、实际安装和file://专属剪贴板权限不在本轮范围。

## 实际验收

设计修改后，27项Python离线回归与13组模拟DOM场景全部通过。现有Edge插件中检查了桌面预览、14.90元输入同步、插画加载，以及375/320 CSS像素容器；餐单完整、无横向溢出。README素材相对路径与章节链接检查通过；本地近似GitHub排版的首屏、封面导出图和预览页面已进行视觉检查。核心Python脚本与Skill未改，尚未提交或推送。

## 2026-10-24：案例展示与阅读体验

本轮由Codex完成，延续现有插画和深咖／奶油配色，没有新增WorkBuddy开发工作。上面的验收与发布描述属于当时记录。

README将历史效果体验、实际Skill接入与开发命令分层，补充目标用户和可展开问答。新素材 `assets/meal-decision-board.svg` 是可缩放的代码排版矢量图，数据只来自公开的 `examples/batch-verification.md`：14.90 / 22.90 / 26.90元，第一份使用可乐，与批量报告一致。早期单工具案例中的柠檬红茶版本保留在原有摘要与预览中。

新图并列展示整单价格、预算余量与组成差异：14.90到22.90元同时换汉堡并增加薯条；22.90到26.90元换汉堡，中薯条和可乐不变。图示不把整单差额当作单品售价，不公开门店、编号或核价时段。

本轮现有Edge Browser Use通道返回“Local browser use is disabled in Work settings”，未能进行插件页面验收。没有切换桌面控制或其他浏览器自动化方式。素材渲染、相对链接及内容一致性检查单独记录，不将其写成GitHub实机排版验收。

离线检查：11个SVG可按XML解析；61个本地Markdown／HTML链接目标和8个章节锚点有效。新图已渲染为1400像素原尺寸及914像素宽的README参考图，人工检查无文本裁切。当前受跟踪文本与新SVG未检出已知个人姓名、门店名称／编号或常见凭据格式；未检查旧Git历史，也未读取私人原始记录。这只是限定范围的静态检查，不是完整安全审计。

官方 `CONTEST_DECLARATION.md` 与本机文件逐字节一致；两份公开MCP配置均使用环境变量占位符。本轮没有修改Skill、Python或交互页面逻辑，没有重新运行历史51项回归，也没有新增MCP请求、安装或发布。
