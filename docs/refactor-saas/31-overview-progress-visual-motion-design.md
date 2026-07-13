# Overview 分析进度画布：视觉与动效升级设计

更新时间：`2026-07-13`

状态：`design_proposal`。本文定义项目总览（Overview）中小说导入后分析进度界面的目标视觉、动效编排和实施切片，不表示当前实现已完成。

## 1. 背景与问题诊断

当前 Overview 的分析进度由三块拼接而成，视觉上是静态平铺清单，状态变化只有颜色瞬间切换（“亮一下”），没有任何过渡、层次或叙事感。

### 1.1 现状代码事实

| 问题 | 位置 | 事实 |
|---|---|---|
| 11 个阶段完全平铺 | `apps/web/components/workflow-progress.tsx:41-49` | `<ol>` 渲染全部阶段为等权重行，无论完成与否全部同屏展示 |
| 状态切换无过渡 | `apps/web/app/globals.css:6910-6931` | `li[data-state]` 只切换 `border-left-color` 和字重，无 `transition`，也无入场动画 |
| 进度条为原生元素 | `apps/web/app/globals.css:2877-2900` | `<progress>` 8px 圆角条，填充值跳变，无法平滑过渡 |
| 双进度面板重复 | `apps/web/components/overview-seed-shell.tsx:379-416` | `WorkflowProgress`（标题+阶段清单）与 `SeedRunOverview`（状态+百分比+进度条）上下堆叠，状态与百分比出现两次 |
| 数据 3 秒跳变 | `apps/web/components/seed-run-auto-refresh.tsx:20-33` | `router.refresh()` 每 3s 全量刷新 RSC，百分比从 24% 直接跳到 42%，无补间 |
| 失败显示 100% | `apps/web/components/overview-seed-shell.tsx:1048-1050` | `seedDisplayProgress` 对 `failed` 返回 `100`，与文档 29 §7“失败保留最后确认进度”直接冲突 |
| 当前阶段无主视觉 | `overview-seed-shell.tsx:404-407` | 当前阶段只是清单里一行变红，没有“当前正在做什么”的播报位 |

### 1.2 已有可复用资产

- 语义 token：`--motion-fast/standard/slow`、`--ease-natural`（`globals.css:51-54`）。
- 动效先例：`worldline-module-reveal`（淡入+位移，`globals.css:407`）、`writer-run-pulse`（活跃点脉冲，`workbench-polish.css:687`）、`writer-skeleton-shimmer`（shimmer 且已按 reduced-motion 门控，`workbench-polish.css:1937-1946`）、`workspace-route-enter`（路由入场，`globals.css:4423`）。
- 纸墨设计系统：暖纸 `#f3eee4` / 面板 `#f7f2e9` / 印章红 `#8f211b` / 旧金 `#a9854f` / 宋体标题。

## 2. 与既有文档的分工

- `26-frontend-ux-optimization.md`：定义了信息分层与共享组件（`WorkflowProgress` 属于公共组件清单），本文不改变该结构结论。
- `29-seed-sse-live-progress-experience.md`：定义数据层（SSE 事件契约、状态机、进度口径、6/11 阶段折叠、动效表 §11.2）。**本文是其视觉与动效层的落地细化**，并补充一个关键点：**Phase 1 完全运行在当前 3s 轮询模型上，不依赖文档 29 的任何后端改造**；文档 29 的 SSE 落地后，本文的视觉层直接换数据源，不重做界面。
- 冲突裁决：动效语义、进度真实性规则（不伪造进度、单调前进、失败不满格）以文档 29 为准；视觉结构、CSS 实现、组件边界以本文为准。

## 3. 目标

- 把“平铺清单 + 重复面板”合并为**一张进度画布**：一个视觉容器回答“做到哪了、正在做什么、接下来是什么”。
- 每一次状态变化都有**方向感**的动效：阶段播报滑入、进度填充推进、数字缓动上升、完成节点落章。
- 高级感来自克制：全程只用 `transform` / `opacity`，一屏最多一个持续动画，纸墨色相不变，无发光、无彩纸、无营销插画。
- 3s 轮询下依然流畅：跳变数据经过显示层补间，视觉连续。
- `prefers-reduced-motion` 下信息零损失。

## 4. 非目标

- 不实现 SSE / 上传字节进度 / 断线恢复（归文档 29 Slice A/B）。
- 不改变 Seed pipeline 阶段语义与事件写入。
- 不引入动画库（framer-motion 等）；`apps/web` 保持零新增运行时依赖。
- 不做暗色主题、不换色相、不加大圆角（半径上限维持 `--radius-panel: 8px`）。

## 5. 设计概念：进度画布（Progress Canvas）

一个 run 的生命周期在同一容器内演进，四个视觉层自上而下：

```text
┌────────────────────────────────────────────────────────────────┐
│ ① 标题行   故事分析                     进行中 · [取消] [重试] │
│                                                                │
│ ② 主播报   42%   正在顺序精读                                  │
│            └ 大号衬线数字（缓动）  └ 阶段播报（滑入切换）      │
│                                                                │
│ ③ 阶段轨道 ●━━━●━━━◉╌╌╌○╌╌╌○╌╌╌○                              │
│            提取 分段 精读 聚合 结构 完成                        │
│            └ 完成节点=红章实心点+勾，连接线随进度填充          │
│                                                                │
│ ④ 活动行   已精读第 94 个片段 · 更新于 12:09:03                │
│            └ 单行原位更新，新文案淡入上滑                      │
└────────────────────────────────────────────────────────────────┘
```

### 5.1 桌面布局（≥ 861px）

```text
┌──────────────────────────────────────────────────────────────────────┐
│ 故事分析                                        进行中    [取消任务] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   42%      正在顺序精读                                              │
│  （宋体特大号，tabular-nums）（阶段播报位，切换时上滑淡入）          │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━─────────────────────────────────  │
│                                                                      │
│  ●────────●────────◉────────○────────○────────○                      │
│  提取文本  智能分段  顺序精读  理解结构  整理档案  建立资产           │
│                                                                      │
│  最新活动：已完成智能分段 · 12:08:54                                 │
└──────────────────────────────────────────────────────────────────────┘
```

- 默认展示 **6 个作者阶段**（映射见 §6.2），11 个技术阶段进入现有“进度与活动详细信息”折叠区，替换当前平铺清单。
- 画布替代现有 `WorkflowProgress` + `SeedRunOverview` 双面板；状态、百分比、进度条各出现一次。

### 5.2 移动布局（≤ 860px）

```text
故事分析              进行中
42%
正在顺序精读

━━━━━━━━━━━━──────────

● 提取文本
● 智能分段
◉ 顺序精读        ← 活跃节点带呼吸脉冲
○ 理解故事结构
○ 整理角色与档案
○ 建立资产并完成

最新活动：已完成第 94 个片段
[取消任务]
```

- 轨道纵向化（与文档 29 §5.2 一致），`375px` 无横向滚动，触控目标 ≥ `44px`。

## 6. 阶段轨道规范

### 6.1 节点状态

| 状态 | 视觉 | 动效 |
|---|---|---|
| `pending` | 8px 空心圆点，`--border-strong` 描边，标签 `--text-muted` | 无 |
| `active` | 10px 印章红实心点 + 外圈呼吸脉冲，标签 `--text-primary` 加粗 | 激活瞬间 `scale(0.6→1)` + 淡入 220ms；`running` 期间低频脉冲（§7.5） |
| `done` | 红点渐变为 `--accent-success` 底、白色 Check 图标 | 点→勾 crossfade 180ms；勾用 `stroke-dashoffset` 描画 240ms |
| `failed` | `--accent-danger` 底 + X 图标，节点后连接线停止填充 | 淡入 180ms，不抖动 |

### 6.2 6 作者阶段 ↔ 11 技术阶段映射

沿用文档 29 §7 折叠口径：

| 作者阶段 | 技术阶段（`SEED_PIPELINE_STAGE_ORDER`） |
|---|---|
| 提取文本 | `parse_file` |
| 智能分段 | `segment_text` |
| 顺序精读 | `sequential_reading` |
| 理解故事结构 | `persist_runtime_facts`、`global_aggregation`、`story_ontology` |
| 整理角色与档案 | `entity_resolution`、`agent_profiles`、`archive_candidates` |
| 建立资产并完成 | `index_assets`、`finalize` |

作者阶段状态 = 其技术阶段状态聚合（任一 `failed` → `failed`；全部 `done` → `done`；任一 `active`/部分 `done` → `active`）。映射函数与现有 `seedPipelineStages()` 同文件放置，纯函数可单测。

### 6.3 连接线

- 节点间连接线为 2px 轨道；完成段用 `transform: scaleX` 从左向右填充（`transform-origin: left`），颜色 `--accent-success` 至 `--accent-primary` 的墨色过渡。
- 活跃段（active 节点之前的半段）填充至节点处停止；不做无限流动光效。

## 7. 动效编排规范

### 7.1 新增 token（`globals.css :root`）

```css
--motion-deliberate: 480ms;                      /* 数字缓动、连接线填充 */
--ease-entrance: cubic-bezier(0.16, 1, 0.3, 1);  /* 播报滑入，克制的 expo-out */
--stagger-step: 50ms;                            /* 画布分层入场步进 */
```

其余一律复用 `--motion-fast/standard/slow` 与 `--ease-natural`。

### 7.2 编排总表（扩展文档 29 §11.2，不与其冲突）

| # | 触发 | 动效 | 时长 / 缓动 | 约束 |
|---|---|---|---|---|
| 1 | 画布首次出现（run 启动或进入页面时有活跃 run） | 标题行→主播报→轨道→活动行依次淡入上滑（`translateY(6px→0)`） | 每层 220ms，步进 `--stagger-step` | 总时长 < 500ms；仅首次挂载，轮询刷新不重播 |
| 2 | 百分比变化 | 显示值从旧确认值缓动到新确认值 | `--motion-deliberate`，rAF 补间 | 只向确认值靠近，永不超前、永不回退（§9） |
| 3 | 进度条填充 | `scaleX` 过渡 | 480ms `--ease-natural` | `transform-origin: left`；与数字缓动同步 |
| 4 | 活跃阶段切换 | 新阶段文案上滑淡入（`translateY(10px→0)`），旧文案原地淡出 | 入 280ms `--ease-entrance`，出 160ms | 双缓冲同格堆叠（§7.4），容器高度固定不回流 |
| 5 | 节点完成 | 红点 crossfade 为绿底 Check，勾描画 | 180ms + 240ms | 同屏只动一个节点 |
| 6 | 连接线推进 | 完成段 `scaleX` 填充 | 480ms | 与节点完成动效衔接（延迟 120ms） |
| 7 | 新活动文案 | 单行原位替换：旧行淡出、新行淡入上滑 | 220ms | 不插入新 DOM 行、不推挤布局 |
| 8 | 成功终态 | 进度满格 → 主播报 crossfade 为“分析完成” + 绿色对勾 → “查看资产”CTA 上滑入 | 280ms 序列 | 无彩纸、无爆炸；CTA 是唯一新增焦点 |
| 9 | 失败终态 | 失败节点定格红 X，错误摘要区淡入 | 180ms | 保留最后确认进度；不抖动页面 |
| 10 | `queued`（准备分析） | 进度条不确定态：纸纹 shimmer 缓慢横移 | 1.4s 循环 | 复用 `writer-skeleton-shimmer` 参数；文案“准备分析”，不显示排队（29 §4.2） |

### 7.3 实现原则

- 全部动效仅 `transform` + `opacity`；禁止宽高/margin 动画，禁止触发 layout 的属性。
- 进度条、数字、轨道均预留固定尺寸，任何更新 CLS 贡献为 0。
- 一屏同时运行的持续动画 ≤ 1 个（active 节点脉冲或不确定态 shimmer，二者互斥出现）。

### 7.4 阶段播报双缓冲

播报位用 grid 单格堆叠避免高度跳动：

```css
.workflow-progress-announcer { display: grid; }
.workflow-progress-announcer > * { grid-area: 1 / 1; }
```

React 侧以 `key={activeStageId}` 触发入场动画；上一条文案由退场副本渲染 160ms 后卸载（`onAnimationEnd`）。基线实现可先做“仅入场”（旧文案直接卸载），双缓冲作为增强。

### 7.5 活跃节点脉冲

复用 `writer-run-pulse` 模式（box-shadow 外扩环），改为印章红、周期 2.4s、外扩 ≤ 6px：

- 仅 `status === "running"` 且节点 `active` 时启用；
- `prefers-reduced-motion: reduce` 下移除（先例：`workbench-polish.css:693`）;
- `queued` 状态不启用脉冲，只有不确定态 shimmer。

这是画布中唯一允许的持续动画，表达“真实在运行”，符合文档 29 对 reconnecting 呼吸点的同类许可；页面隐藏时暂停归入 P2（`document.hidden` 时置 `animation-play-state: paused`）。

### 7.6 数字缓动 hook

新增 `apps/web/lib/use-animated-number.ts`（客户端，~40 行）：

- rAF 补间 `displayed → target`，时长 `--motion-deliberate`，ease-out；
- `matchMedia("(prefers-reduced-motion: reduce)")` 命中时直接赋终值；
- 目标值小于当前显示值时不回退（同 attempt 内），直接钳制（§9）；
- 数字容器 `font-variant-numeric: tabular-nums`（先例 `globals.css:2874`），避免宽度抖动。

不采用 CSS `@property` 数字过渡方案：Firefox 版本覆盖与 `counter()` 渲染一致性不足，rAF 方案 40 行内可控。

## 8. 组件与代码落点

### 8.1 契约测试约束（不可破坏）

| 契约 | 位置 | 含义 |
|---|---|---|
| `overview-seed-shell.tsx` 必须 `import` 自 `"./workflow-progress"` 且渲染 `<WorkflowProgress` | `tests/frontend-ux-completion-contract.test.mjs:57-60` | 组件名与模块路径保持不变，在内部升级 |
| `globals.css` 必须存在 `.workflow-progress {` | `frontend-ux-foundation-contract.test.mjs:36`、`frontend-ux-completion-contract.test.mjs:146` | 根类名不变，新增子类并存 |
| `workflow-progress.tsx` 在内容边界白名单内 | `tests/content-boundary-contract.test.mjs:24,146` | 升级后不得输出 UUID、原始 JSON、内部错误码 |

### 8.2 文件边界

| 文件 | 变更 | 职责 |
|---|---|---|
| `components/workflow-progress.tsx` | 重构（保留导出名与 props 兼容） | 进度画布容器；新增可选 props：`progressValue?: number`、`status?: string`、`indeterminate?: boolean`、`completedCta?: ReactNode` |
| `components/workflow-progress-client.tsx` | 新增（`"use client"`） | 数字缓动、阶段播报双缓冲、入场编排等需要状态的子层；由 `workflow-progress.tsx` 组合 |
| `components/workflow-stage-track.tsx` | 新增 | 6 作者阶段轨道（节点+连接线），纯展示 |
| `lib/use-animated-number.ts` | 新增 | §7.6 |
| `components/overview-seed-shell.tsx` | 修改 | 删除 `SeedRunOverview` 重复面板（`:948-996`），状态/百分比/失败提示并入画布；新增 6 阶段聚合映射；修复 `seedDisplayProgress` failed→100 |
| `app/globals.css` | 修改 | `.workflow-progress` 块内新增画布/轨道/播报/终态样式与 keyframes；新增 §7.1 token |

保持服务端优先：`workflow-progress.tsx` 仍可被 RSC 渲染（首屏 snapshot 直出），客户端子组件仅负责动效状态，hydration 前后 DOM 结构一致，不出现“先清空再动画”。

### 8.3 详情折叠区

现有“进度与活动详细信息”`<details>`（`overview-seed-shell.tsx:238-265`）保留，内部的 11 阶段清单改为复用 `workflow-stage-track.tsx` 纵向密排形态（带各技术阶段状态点），替换当前左边框行样式。

## 9. 进度真实性规则（继承文档 29）

- 显示值只向**已确认**值补间，永不超过确认值；不做“每秒 +1% 假忙碌”。
- 同一 attempt 内显示值单调不减；retry 产生新 attempt 时允许重置并明示“第 N 次尝试”。
- `failed` 保留最后确认进度：**P1 必须修复** `seedDisplayProgress`（`overview-seed-shell.tsx:1048`）中 `failed` 返回 `100` 的行为，改为返回 `max(run.progress, fromEvents)`，并在播报位显示“在「{阶段}」中断”。
- `queued` 文案统一“准备分析”，不确定态视觉，不显示队列人数或 ETA。
- 轮询模型下阶段推进以事件（`seedEvents`）为准，与现有 `seedPipelineStages()` 逻辑一致，仅改渲染层。

## 10. 可访问性与 Reduced Motion

- 进度条：`role="progressbar"` + `aria-valuemin/max/now`（替换原生 `<progress>` 后必须补齐）；不确定态不设 `aria-valuenow`，文字“准备分析”。
- 容器保留现有 `aria-live="polite"`（`workflow-progress.tsx:32`），但播报内容收敛为阶段切换与终态，百分比数字容器加 `aria-hidden` 的补间层 + 视觉隐藏的真实值文本，避免读屏逐帧轰炸。
- 节点状态同时用图标（勾/叉）+ 文案 + 颜色表达；对比度：正文 ≥ 4.5:1，状态图形 ≥ 3:1。
- 失败摘要 `role="alert"`。
- `prefers-reduced-motion: reduce`：所有过渡/补间/脉冲/shimmer/入场编排全部关闭，状态即时切换，信息与布局完全一致（先例模式：`workbench-polish.css:1937` 用 `no-preference` 正向门控，新动效一律采用正向门控写法）。

## 11. 实施切片

### P1 — 进度画布（纯前端，运行在现有 3s 轮询上）

1. 新增 token 与 `use-animated-number.ts`。
2. 重构 `workflow-progress.tsx` 为画布结构（标题行/主播报/轨道/活动行），新增 client 子组件与 `workflow-stage-track.tsx`。
3. `overview-seed-shell.tsx`：合并 `SeedRunOverview`、接入 6 阶段聚合、修复 failed→100、`queued` 文案改“准备分析”。
4. CSS：画布样式、节点/连接线、播报双缓冲、终态编排、reduced-motion 门控；详情区 11 阶段密排形态。
5. 验证：`npm test && npm run typecheck && npm run build`（契约测试 §8.1 必须全绿）。

### P2 — 实时数据接入（依赖文档 29 Slice A/C 落地）

1. 数据源从 3s `router.refresh()` 切换为 SSE reducer 输出，`SeedRunAutoRefresh` 退役。
2. 阶段内 `completed_units / total_units` 进入主播报副行（“已处理 94 / 302 个片段”）与连接线细分填充。
3. 连接状态点（实时同步/重连中）挂到标题行；`document.hidden` 暂停装饰动画。
4. 活动行升级为文档 29 §12 的活动 Feed 映射。

### P3 — 画布复用

1. `story-graph-shell.tsx` 构建进度（`:238-242` 现为标题+百分比文本）换用同一画布。
2. Worldline 推演与 Writer run 依据各自阶段模型接入 `WorkflowProgress` 新 props，兑现其“shared long-running task surface”注释的原始意图（当前唯一消费方是 overview，`workflow-progress.tsx:19-21`）。

## 12. 验收标准

- 一个活跃 run 在 Overview 中只有一个进度容器；状态、百分比、进度条各出现一次。
- 阶段切换时：新阶段文案 280ms 上滑淡入，节点点亮，连接线推进；无任何元素瞬跳。
- 3s 轮询下百分比与进度条平滑推进；显示值不超前、不回退。
- `failed` 不再显示 100%；保留最后确认进度并标注中断阶段。
- `queued` 显示“准备分析”+ 不确定态，无排队文案。
- 完成时刻：满格 → 播报切换 → CTA 滑入的完整编排 ≤ 800ms，无彩纸类效果。
- `prefers-reduced-motion: reduce` 下无任何动画，信息完整。
- `375 / 768 / 1024 / 1440` 无横向溢出；进度更新 CLS < 0.1；动画期间无 layout thrash（DevTools Performance 验证 paint-only）。
- 纸墨红金色相、宋体标题、8px 半径边界不变；契约测试（§8.1）与 `tsc --noEmit`、`npm run build` 通过。

## 13. 测试矩阵

### 单元 / 契约（`apps/web/tests`）

- `workflow-progress` 画布结构快照：hero 数字、播报位、6 节点轨道、活动行存在。
- 6↔11 阶段聚合纯函数：done/active/failed 聚合、乱序事件、未知 stage 忽略。
- `seedDisplayProgress`：failed 保留最后进度（回归用例）；单调钳制。
- `use-animated-number`：向上补间、目标回退钳制、reduced-motion 直达。
- 既有 `frontend-ux-completion-contract` / `foundation-contract` / `content-boundary-contract` 不修改断言前提下通过。

### 浏览器 live（`seed-upload-browser-live` 延伸）

- 启动分析后画布入场编排出现一次且不重播。
- 阶段推进时节点/连接线/播报变化可见，无页面跳动。
- 取消、重试、完成三种终态视觉正确；完成后 CTA 可达资产页。
- 强制 reduced-motion 后截图对比：布局一致、无动画。
- `375 / 768 / 1024 / 1440` 四视口截图归档。

## 14. 风险与回退

| 风险 | 缓解 |
|---|---|
| 轮询全量 RSC 刷新导致 client 子组件状态丢失 | 动效状态全部保存在 client 组件内部（`useRef`/`useState`），RSC 刷新只更新 props；`key` 只绑定 `runId`，不绑定进度值 |
| React 树 reconcile 时节点被卸载重建导致动画重播 | 画布与节点 `key` 稳定为 stage id；入场编排用挂载标记 ref 保证仅首次 |
| 双缓冲播报在快速连续阶段切换时堆叠 | 退场副本上限 1 条，新切换直接替换未完成的退场副本 |
| 契约测试对类名/导入路径的隐性依赖 | §8.1 列出的三处契约在 P1 第 5 步显式验证；重构不改导出名与根类名 |
| P2 前后数据源切换引起视觉回退 | 画布只消费统一的 `{status, progress, stages, activity}` 视图模型，P2 仅替换视图模型生产者 |
