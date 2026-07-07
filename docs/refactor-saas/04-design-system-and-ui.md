# 04. Design System and UI

更新时间：`2026-06-27`

## UI 目标

新界面要服务“作者长期工作”，不是展示型 landing page。视觉方向应是：

- 专业。
- 高密度但不杂乱。
- 创作工具感。
- 工作流清晰。
- Agent 过程透明。
- 图谱和素材可读。
- 移动端可用，桌面端优先。

旧前端问题：

- 每个页面都在局部堆功能，缺少统一信息架构。
- 图谱页面同时承担构建、概览、筛选、选择、羁绊生成和档案生成，视觉焦点混乱。
- 资产库涵盖内容丰富，但资产类型、来源、生命周期、候选/正典关系需要更清晰。
- worldline、character console、writer 三个页面概念有关联，但入口和数据流割裂。
- UI primitives 已有重构痕迹，但还缺少产品级 design system。

## 总体信息架构

### SaaS 顶层

```text
Marketing / public docs
Auth
Tenant switcher
Tenant settings
Project list
Project workspace
Admin / billing
```

### 项目工作台

每个项目内固定一级导航：

```text
总览
导入与分析
故事图谱
资产库
世界线
角色控制
写作台
设置
```

旧 `/guide` 变成：

- 空状态引导。
- 帮助中心。
- 每个模块内的轻量说明。

旧 `/llm-facility` 变成：

- 租户设置里的 `LLM 设施`。
- 项目设置里的 `模块绑定覆盖`。

## 全局 App Shell

桌面端：

```text
Left Sidebar
  tenant switcher
  project switcher
  primary nav
  secondary settings

Top Bar
  breadcrumb
  current project status
  command palette
  LLM activity
  user menu

Main Surface
  module workspace
```

移动端：

- 顶部 project switcher。
- 底部 4-5 个主要模块：总览、资产、世界线、写作、更多。
- 图谱和写作台在移动端降级为可审阅/轻编辑，不承诺完整大型操作。

## 视觉系统

### 风格

推荐“专业创作操作台”：

- 背景浅色为主，暗色主题可选。
- 中性灰 / 墨蓝作为结构色。
- 绿色用于完成和正典。
- 琥珀用于候选和待审。
- 红色用于错误和危险。
- 紫色/蓝色只作少量语义强调，不做全站主色泛滥。

### 色彩 token

```text
--surface-app
--surface-panel
--surface-subtle
--border-default
--border-strong
--text-primary
--text-secondary
--text-muted
--accent-primary
--accent-success
--accent-warning
--accent-danger
--accent-candidate
--accent-canon
--accent-simulation
--accent-agent
```

### 字体

推荐：

- UI：Geist Sans 或 Inter。
- 数字/任务编号/trace：Geist Mono 或 JetBrains Mono。
- 正文阅读：可配置中文阅读字体，如 `Noto Serif SC` / 系统宋体 fallback。

规则：

- 工作台标题不要 hero 化。
- 控制面板内标题小而清晰。
- 正文阅读区域 line-height 1.7 左右。
- 按钮、tabs、badge 不使用过小文字。

### 圆角和密度

- 默认圆角 6-8px。
- 卡片只用于重复 item、详情 panel、modal，不把整页套进大卡片。
- 页面 section 用 full-width band 或 unframed layout。
- 工具按钮使用 icon button + tooltip。
- 主要操作必须有文字。

## 通用组件

### Project Context Bar

显示：

- 当前项目名。
- seed 状态。
- graph 状态。
- asset count。
- active workflow。
- 最近 writer run。

### Workflow Progress Surface

统一展示长任务：

- 当前阶段。
- 总进度。
- 子阶段列表。
- 最近事件。
- 错误和恢复动作。
- trace drawer。
- cancel / retry / resume。

旧 seed timeline、graph build console、worldline auto task panel、writer progress panel 都应收敛到同一组件族。

### Agent Trace Drawer

统一展示：

- prompt snapshot。
- tool calls。
- tool results。
- LLM model。
- token usage。
- latency。
- JSON parse/repair。
- error stack。

敏感内容默认折叠，查看大段原文需要权限和审计。

### Inspector Panel

用于：

- 图谱节点/边。
- 资产详情。
- worldline 事件。
- 角色档案。
- writer tool result。

结构：

```text
Header
  title
  lifecycle / status
  actions
Tabs
  Summary
  Evidence
  Relations
  Memory
  Trace
```

### Command Palette

全局支持：

- 切换项目。
- 搜索资产。
- 跳转章节。
- 启动图谱构建。
- 启动 worldline。
- 打开 LLM 设置。

旧 writer command palette 可以升级为全局命令系统。

## 页面布局规范

### 总览

目标：让作者知道“现在项目到了哪一步，下一步做什么”。

布局：

- 顶部项目健康摘要。
- 主操作区：上传/继续分析/查看最新结果。
- 任务流：seed/graph/writer/worldline 最近 workflow。
- 数据就绪度：角色、关系、世界规则、资产、章节、worldline。
- 最近活动。

### 故事图谱

目标：把“乱图”变成可读的故事世界地图。

布局：

- 左侧：图谱模式、图层、过滤、搜索。
- 中央：React Flow 画布。
- 右侧：Inspector。
- 顶部：构建状态、当前视图、布局控制、证据开关。
- 底部可选：选中节点篮子，用于生成羁绊/支线。

模式：

- Explore：浏览。
- Build：构建/重建。
- Curate：合并、隐藏、标记正典。
- Compose：选节点生成羁绊/支线。

### 资产库

目标：成为小说系统所有内容的统一入口。

布局：

- 顶部搜索 + 新建/入库。
- 左侧 facets：来源、类型、生命周期、项目、标签、角色/组织/规则/线索。
- 中央结果：列表/卡片/看板。
- 右侧详情：内容、结构化字段、关联、使用历史、记忆。

### 世界线

目标：作者做剧情实验。

布局：

- 左侧：选择角色/档案/世界变量。
- 中央：推演控制和当前世界状态。
- 右侧：候选事件、timeline、保存/采用。

### 角色控制

目标：作者第一人称进入某个角色，在当前节点互动写作。

布局：

- 左侧：session、角色、降临节点。
- 中央：互动对话/动作流。
- 右侧：角色状态、记忆、当前场景约束。
- 底部：转写为章节草稿。

### 写作台

目标：主写作界面。

布局：

- 左侧：章节/场景目录。
- 中央：正文编辑器。
- 右侧：上下文、Agent trace、审校、资产引用。
- 顶部：写作模式、模型状态、保存状态、运行按钮。

## 交互原则

- 每屏只有一个主要动作。
- 长任务按钮必须有 disabled/loading/error 状态。
- 所有 destructive action 要确认。
- 表单字段必须有 label。
- 空状态必须给出下一步动作。
- trace 和高级设置默认折叠。
- 切换页面要保留过滤、滚动和当前选择。
- 工作台三栏布局必须支持折叠。

## 图标规范

使用 lucide-react：

- 总览：`LayoutDashboard`
- 导入分析：`UploadCloud` / `ScanText`
- 图谱：`Network`
- 资产：`Library`
- 世界线：`GitBranch`
- 角色控制：`UsersRound`
- 写作：`PenLine`
- LLM：`Cpu`
- Trace：`Activity`
- 审计：`ShieldCheck`

禁止使用 emoji 做导航图标。

## Accessibility

必须满足：

- 键盘可操作。
- icon-only button 有 aria-label 和 tooltip。
- 颜色不是唯一状态表达。
- focus ring 可见。
- 正文对比度达标。
- 图谱节点可通过搜索和列表替代访问。
- SSE 动态状态用 aria-live 或等价方式告知。

## 前端验收

- 375px、768px、1024px、1440px 下无横向滚动。
- 长中文标题不会溢出按钮或卡片。
- 任务进度不会因文本变化导致布局跳动。
- 图谱 1000 节点时不卡死，默认聚合/分页/局部展开。
- 写作台正文区域不会被 fixed header/footer 遮挡。
- LLM 未绑定时，每个模块给出明确配置入口。
