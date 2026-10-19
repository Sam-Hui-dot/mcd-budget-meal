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
