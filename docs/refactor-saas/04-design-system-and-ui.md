# 04. Design System and UI

更新时间：`2026-07-12`

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

采用 **现代书卷式创作工作台**。Google、Microsoft、Apple 和 Amazon / Cloudscape 只提供信息层级、导航、筛选、渐进披露和响应式结构参考，不复制它们的配色、字体、材质或品牌外观。

- 保留小说产品的视觉识别：暖纸、深墨、印章红、克制旧金、宋体标题和低对比纸纹。
- 纸面承载阅读、表单和正文；墨面只承载主画布、当前选中对象或沉浸式 Agent / Inspector，不在同页平铺多个深色视觉中心。
- 首屏直接进入创作任务。Overview 可保留较强叙事画面，Assets、Graph、Worldline、Character、Writer 等工作台使用紧凑页头。
- 视觉高级感来自比例、留白、字阶、细线分隔和稳定交互，不来自大面积玻璃、营销式 hero、装饰性渐变或卡片堆叠。
- 每页只突出一个主对象和一个主要动作。红色不作为普通按钮的默认填充色泛滥使用。

整体气质应像一套当代编辑部与作家长期使用的数字案头：有文学辨识度，同时保持专业工具的效率和可扫描性。

### 纸墨材质层级

```text
App background
  暖纸色 #f3eee4 / #e9e3d8 + 极低对比度纸纤维纹理

Navigation paper
  稳定浅纸面 + 深墨文字 + 细线分隔
  当前项使用左侧印章红标记，不使用大面积填色

Primary panel
  近实色暖纸面；4-8px radius；优先使用分隔线而不是投影

Ink surface
  #171a1b 一类深墨面；旧金用于少量结构线和状态点
  用于图谱画布、选中对象 Inspector 或沉浸创作区域

Controls
  4-6px radius；桌面 40px、触控 44px 高；focus ring 使用印章红
```

任何正文、错误信息和表格文字都不得依赖纹理或透明背景维持对比度。纸纹只作为低对比装饰层，不得降低可读性。

### 颜色策略

基础方向：

- 暖纸色为主，深墨色用于结构和局部沉浸面。
- 印章红 `#8f211b` 用于唯一主操作、选中态和焦点环。
- 旧金 `#a9854f` / `#b18a4e` 只用于分隔、候选和少量层级强调。
- 绿色用于完成和正典。
- 琥珀用于候选和待审。
- 红色用于错误和危险。
- 紫色仅在确有语义区分时使用，不作为背景装饰。

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

- UI 控件：`Noto Sans SC` / `Microsoft YaHei UI` / 系统无衬线 fallback。
- 标题与创作内容：`Songti SC` / `SimSun` / `Noto Serif SC` / Georgia fallback。
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

### 动效

- 交互时长使用 160ms、220ms、280ms 三档，常规状态变化优先 220ms。
- 使用统一的自然减速曲线；动效服务展开、选中、保存和层级变化。
- panel 悬停最多上浮 1px；按钮按下最多位移 1px，不使用弹跳或大比例缩放。
- 动画只改变 `transform`、`opacity`、颜色和阴影，避免触发布局抖动。
- 所有非必要动画必须在 `prefers-reduced-motion: reduce` 下关闭。
- 进度和状态变化应保留文本，不依赖渐变或颜色单独表达语义。

### Web 适配边界

- 桌面端使用固定宽度导航 rail + 顶部 context bar + 自适应主工作区。
- 触控目标最小 44px；数据密集表格可横向滚动，但页面本身不得横向溢出。
- 小于 860px 时导航折叠为顶部抽屉，主工作区和双栏 panel 变为单列。
- 长表单和受权限控制的诊断输出保持在所属 Drawer 内滚动，不建立嵌套页面滚动区。
- 页面 header 保持无卡片、紧凑且可扫描；panel 标题不得使用 hero 尺寸。

## 通用组件

### Project Context Bar

默认只显示当前项目、当前主链阶段、唯一活动任务摘要、全局搜索和用户菜单。Seed、Graph、资产数量和最近 Writer run 等完整状态进入“项目状态” Popover，不平铺成一排状态 pill。

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

### Technical Details Drawer

只对有权限的支持或管理员角色按需加载：

- prompt snapshot。
- tool calls。
- tool results。
- LLM model。
- token usage。
- latency。
- JSON parse/repair。
- error stack。

普通作者 UI 不渲染 UUID、原始 JSON、系统 Prompt、Provider 请求响应、内部错误码、数据库/队列/Worker 信息。敏感内容不能只靠 CSS 隐藏；作者 API 投影本身不得返回。查看大段原文需要权限、主动操作和审计。

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
  Technical details（仅授权角色）
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

- 顶部单行 Filter Bar：搜索、已启用条件、筛选入口、排序、视图。
- 来源、类型、生命周期、项目、标签、角色/组织/规则/线索在统一 Popover / Sheet 内分组编辑；应用后显示为可移除 chips。
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

- 左侧主区：连续 Agent thread，依次呈现作者指令、检索活动、工具结果、候选正文和人工决策。
- 主区底部：常驻 composer；写作模式使用 segmented control，上下文引用作为附件渐进披露。
- 右侧：稿件 artifact，通过 `稿件 / 章节 / 审校 / 工作室` 互斥标签切换正文、结构、审校、规划与命令。
- 顶部：Writer Agent 状态和技术详情入口；run/trace id、事件游标和回放只进入授权 Drawer。
- 移动端：Agent thread 在前，artifact 在后；不恢复纵向平铺全部表单的旧长页。

## 交互原则

- 每屏只有一个主要动作。
- 长任务按钮必须有 disabled/loading/error 状态。
- 所有 destructive action 要确认。
- 表单字段必须有 label。
- 空状态必须给出下一步动作。
- trace 和高级设置默认折叠。
- 切换页面要保留过滤、滚动和当前选择。
- 工作台三栏布局必须支持折叠。
- 当前任务必需信息不得放进折叠区；高级设置、历史、解释和诊断才使用渐进披露。
- 每项既有用户能力最多通过两层 Disclosure / Drawer / Tabs 可到达，不因简化界面而删除。

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
- 默认筛选栏保持单行，已应用筛选同步 URL，刷新和返回后状态不丢失。
- 作者可见文本和 SSR HTML 不含 README、开发文档路径、UUID、原始 JSON、内部错误码、系统 Prompt 或 Provider Body。
- 每个页面可见区域最多一个 primary action；其余命令降为次要按钮、Overflow Menu 或上下文动作。
