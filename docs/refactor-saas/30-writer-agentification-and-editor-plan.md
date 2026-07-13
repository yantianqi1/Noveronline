# Writer 写作台 Agent 化与编辑器完整方案

更新时间：`2026-07-13`

## 文档职责

本文是写作台（Writer / 写作 Agent）**Phase 1 之后**全部剩余工作的唯一实现蓝图，覆盖真实 Agent 编辑室的编辑器、选区驱动、行内 diff、持久 thread、真实 SSE 推送、审批与视觉验收。

- 范围与最终 DoD 的上位文档：`DEVELOPMENT_PLAN.md`；当前进度快照：`24-current-development-progress.md` 的「并行：Writer Agent 化重构（Agentification）」小节。
- 领域上位设计：`11-writer-workbench.md`、`21-pi-writer-agent-runtime.md`、`04-design-system-and-ui.md`、`26-frontend-ux-optimization.md`。
- 冲突时以当前 worktree、schema、运行中 compose 与本轮测试输出为最终事实。

**方向决策（已确认）**：手稿编辑面采用 **TipTap / ProseMirror**（视觉与能力最好的一条），用隐藏 `<textarea>` 作为表单真源与无 JS 回退以保住渐进增强；重依赖仅出现在手稿编辑器代码路径，通过动态加载 / 代码分割避免拖累基础路由。后端可较大改动（Pi revise 模式、thread 持久化、真实 SSE、审批）。唯一硬要求：**最终效果要好——美观、真实、好用。**

---

## 1. 设计原则

1. **手稿主导的编辑室（manuscript-primary editorial studio）**：手稿画布是主导，Agent 是常驻、可观察的协作者（右侧 dock）。已在 Phase 1 通过 `data-layout="manuscript-primary"` + 三区落地。
2. **真实 Agent**：诚实的工具循环、真实流式、真实审批门控；不做 mock 成功、静默降级、宽泛兜底或吞异常。
3. **渐进增强优先**：server action 表单与 textarea 是无 JS 真源；富编辑器在其上 hydrate，不破坏无 JS 可用性。
4. **美学优先**：暖纸、墨色、印章红、旧金、宋体标题——"现代书卷式创作工作台"。不引入微软蓝、Material 大圆角、Apple 大留白或 AWS 运维台外观。
5. **可验证增量**：每个增量都能独立 typecheck + focused 契约测试 + build 通过后再进入下一个。

### 不可变视觉边界（继承自 `26-frontend-ux-optimization.md`）

- 暖纸色 `#f3eee4` / `#e9e3d8` / `#fbf8f1`（手稿纸面）。
- 深墨色 `#171a1b` 正文，次级墨 `#33302a` / `#4d4a43`。
- 印章红 `#8f211b`（本仓实现取 `#8b2f27`）——唯一主动作、选中态与焦点。
- 旧金 `#a9854f` / `#b18a4e`——少量结构强调。
- 宋体标题与正文阅读感；控件、表格用清晰无衬线。
- 不引入蓝色换肤、大圆角、运维台风格。

---

## 2. 现状：Phase 0 + Phase 1（已 `verified_current`）

- **Phase 0 传输底座**：增量事件轮询（`lib/writer-event-store.ts` normalized store + `/api/writer-events/[tenantId]/[projectId]` route + `components/writer-live-draft.tsx`）替换假串流全页刷新；连接横幅（reconnecting/interrupted + retry）；创建 run 带 `Idempotency-Key`；窄化 aria-live。
- **Phase 1 四区布局**：
  - 1.1 版面反转（手稿画布 `writer-artifact-canvas` 主导 + Agent `writer-agent-dock` 常驻）。
  - 1.2 真·三区（左侧 `WriterStructureNav` 纯导航 GET 表单）。
  - 1.3 ⌘K 命令面板（`writer-workbench-context` 共享 state + `WriterCommandPalette`）。
  - 1.4 顶栏（面包屑 + `WriterRunStateChip` + 已同步指示）。
- **验证基线**：Web 串行 full `250` 项 `241 passed / 9 skipped`；typecheck / build passed。

---

## 3. 目标体验（叙事）

作者在中间手稿画布上直接写作，正文是真实的书卷纸面。选中一段文字，浮出**选区工具条**：改写、扩写、精简、润色、按设定校正。点击后，右侧常驻 Agent 立即开始工作——**活动时间线**逐条显示它读了哪些设定 / 图谱 / 世界线（context chips），正文上以**行内 diff**呈现它的修改建议，作者可**逐块接受 / 拒绝**。接受即写入手稿版本（乐观并发），拒绝则原文不动。整段对话是**持久 thread**，跨会话、跨登录仍在。当 Agent 要写入正典或触发蒸馏这类有后果的动作时，弹出**审批**，作者点头才继续。全过程通过**真实 SSE**流式推送，断线可凭 `Last-Event-ID` 续传，不再整页刷新。

---

## 4. 阶段计划（Phase 2–6）

> 每个 Phase 拆为可独立验证的增量；标注前端 / 后端 / 契约与验收 / 风险。文件路径均在 `apps/web`、`apps/pi-agent-runtime`、`apps/api`、`infra` 下。

### Phase 2 — TipTap 手稿编辑器

**目标**：把 `ManuscriptPanel` 的纯 `<textarea>` 升级为真实 ProseMirror/TipTap 编辑器，保住渐进增强，为选区与行内 diff 打底。

**前端**
- 依赖：`@tiptap/react`、`@tiptap/starter-kit`、`@tiptap/pm`（仅在编辑器组件路径引入）。
- 新组件 `components/writer-manuscript-editor.tsx`（`"use client"`）：
  - TipTap 编辑器绑定当前正文块内容；**隐藏 `<textarea name="content">` 镜像**为表单真源 + 无 JS 回退（编辑器 `onUpdate` 同步写入隐藏 textarea）。
  - 轻工具条：段落 / 强调 / 引用 / 撤销重做——克制，保持小说正文纸面（不做花哨富文本）。
  - 失焦自动保存：`form.requestSubmit()` 触发既有 `updateBlock` server action（`expected_version` 乐观并发不变）。
  - 字数统计、稳定光标、`prefers-reduced-motion` 友好。
  - 用 `next/dynamic`（`ssr: false`）动态加载编辑器主体，服务端先渲染 textarea，客户端 hydrate，**基础路由体积不受重依赖影响**。
- 集成进 `writer-product-workspace.tsx` 的 `ManuscriptPanel`：服务端渲染 textarea → 客户端增强为编辑器。

**后端**：无需改动（正文是文本）。后续如需保存轻量格式再评估（默认纯文本 + 段落）。

**契约与验收**
- 契约：编辑器组件存在；隐藏 `textarea name="content"` 存在（PE 锁）；表单仍 POST `content` + `expectedVersion`。
- 验收：有 / 无 JS 均能编辑并保存；光标稳定；视觉为书卷纸面；基础路由 JS 不因编辑器显著增大（编辑器 chunk 独立）。

**风险**：PE 回退正确性；SSR hydration 一致性；bundle（用动态加载与代码分割化解）。

---

### Phase 3 — 选区驱动调用 + 行内 diff

**目标**：选中正文 → 唤起 Agent（改写 / 扩写 / 精简 / 校正）→ 行内 diff → 逐块接受 / 拒绝 → 接受写入手稿版本。

**前端**
- 选区工具条（TipTap `BubbleMenu` / 自定义 popover）：预设动作 + 自由指令 → 提交一个新的 **revise run**（带选区文本 + 范围 + 指令）。
- 行内 diff 装饰（ProseMirror `Decoration`）：插入 / 删除高亮；逐 hunk 接受 / 拒绝；接受则应用到编辑器并经 `updateBlock` 持久化。
- `components/writer-revision-diff.tsx`（对齐技能 RevisionDiff 规范）：hunk 列表 + 全部接受 / 拒绝。
- diff 应用为**纯函数**（`lib/writer-diff.ts`），便于单测。

**后端（Pi + Go）**
- Pi Writer Agent 新增 **revise 模式**：输入 `{block_id, selection_text, range, instruction}`，输出结构化 hunks（或修订全文 + 服务端/客户端计算 diff）；沿用 `beforeToolCall` 权限门控、只读检索、**不写正典**。
- Go 控制面：revise run 的 admission 与事件 framing（复用 writer run 通道，新增 `mode=revise` 与对应 public event）。
- 契约包 `packages/shared-contracts`：revise 输入 / 输出 schema（Draft 2020-12），Go/Pi/Web 三侧序列化测试 fail-closed。

**契约与验收**
- 契约：revise schema；diff 纯函数单测；popover / 装饰契约（组件 + 类名）。
- 验收：选区 → revise → diff → 接受可持久化；拒绝原文不变；未经 adopt/审批不写正典；乐观并发冲突有显式提示。

**风险**：diff 正确性；hunk ↔ ProseMirror 位置映射；与 `expected_version` 的并发。

---

### Phase 4 — 持久 Agent thread + 活动时间线 + context chips

**目标**：跨会话持久的对话 thread、真实工具调用的活动时间线、Agent 的落地依据（context chips）。

**前端**
- thread 由持久消息渲染（非仅内存）；`components/writer-activity-timeline.tsx`（工具调用 / 检索 / 写入，对齐技能 ActivityTimeline）；`components/writer-context-chip.tsx`（assets / graph / worldline 依据）。
- composer 发到 thread；run 事件挂到 thread 消息。

**后端（Go + Pi + DB）**
- 新表 `writer_threads`、`writer_thread_messages`（Alembic 新 revision，绝不改已应用 revision）；RLS / tenant 作用域；app-role SQL。
- Go：thread 读写路由；run / 事件与 thread 关联。
- Pi：工具循环发出结构化活动事件，映射为时间线条目（公开事件脱敏 rule text / evidence / private metadata）。

**契约与验收**
- 契约：thread schema、消息顺序、RLS 隔离（同租户跨项目 + 跨租户 live）；时间线 / chips 契约。
- 验收：thread 跨刷新 / 重新登录仍在；时间线显示真实工具调用；chips 反映真实检索依据。

**风险**：schema 设计；migration；事件 → 消息映射。

---

### Phase 5 — 真实 SSE 推送 + 审批 + 续传

**目标**：以真正 held-open SSE 推送替换增量轮询；有后果动作的审批门；断线续传。

**前端**
- `EventSource` 客户端：重连 + `Last-Event-ID` 续传；连接状态机（复用 Phase 0 横幅）；SSE 可用时替换 `WriterLiveDraft` 轮询，不可用时优雅回退轮询。
- 审批 UI：Agent 提议写正典 / 触发蒸馏时，行内 approve / reject。

**后端（Go）**
- 真实 SSE 端点：held-open 循环，读 `Last-Event-ID`，事件产生即推（改造现有 `writeWriterEventsSSE` 的 batch-dump 为持续推送，基于 pub/sub 或 poll-forward）。
- 审批工作流：门控有后果的工具调用（Pi `beforeToolCall` 已门控；上升为需用户决策的 approval 事件，决策前阻塞继续）。

**契约与验收**
- 契约：SSE framing、续传语义；approval 事件 schema；回退轮询。
- 验收：无整页刷新的真实流式；断线可续传；审批未决前阻塞。

**风险**：held-open SSE 基础设施（超时、代理缓冲）；背压；审批状态机。

---

### Phase 6 — 视觉打磨 + 可访问性 + 验收

**目标**：最终视觉打磨、可访问性、fresh browser 视觉验收证据。

- 微交互、空状态、加载骨架、焦点环、reduced-motion、键盘全覆盖、屏幕阅读器标签。
- fresh desktop / mobile 截图（需真实登录 + 可用浏览器实例）。

**验收**：a11y 通过；视觉验收截图；性能预算（基础路由 JS、编辑器 chunk 懒加载）。

---

## 5. 视觉与组件规范（确保"美观"落地）

| 组件 | 文件 | 关键规范 |
|---|---|---|
| 手稿编辑器 | `writer-manuscript-editor.tsx` | 纸面 `#fbf8f1`；宋体正文；行高宽松；印章红光标 / 选区；克制工具条；隐藏 textarea 真源 |
| 选区工具条 | `writer-selection-toolbar.tsx` | 浮于选区上方；印章红主动作；≤5 预设 + 自由指令 |
| 行内 diff | `writer-revision-diff.tsx` | 插入=旧金底纹，删除=删除线墨灰；逐 hunk 接受 / 拒绝；全部接受 / 拒绝 |
| 活动时间线 | `writer-activity-timeline.tsx` | 每条=图标 + 动作 + 依据；工具调用 / 检索 / 写入分色；时间顺序 |
| context chip | `writer-context-chip.tsx` | 小圆角标签；assets / graph / worldline 分类；点击定位来源 |
| 审批卡 | `writer-approval-card.tsx` | 明确后果说明 + approve / reject；印章红=approve |

- 复用 Phase 0/1 已建类：`writer-agent-layout` / `writer-artifact-canvas` / `writer-agent-dock` / `writer-structure-rail` / `writer-command-palette` / `writer-run-state-chip`。
- 动效克制，均提供 `prefers-reduced-motion` 降级（如 run-state 脉冲已降级）。

---

## 6. 横切关注

- **性能**：编辑器与重面板 `next/dynamic` 懒加载；基础路由保持精简（当前 writer 路由 7.79 kB，编辑器 chunk 独立）。
- **可访问性**：dialog / listbox / tab roles；`aria-live` 窄化；焦点管理；键盘全覆盖；reduced-motion。
- **隐私 / 安全**：公开事件脱敏；正典写入需 adopt / 审批；thread 表 RLS；prompt / response trace 视为敏感。
- **LLM**：全部经全局 LLM Facility 路由；模块键一致（`writer_reviewer`、`writer_dedup_extractor`，新增 `writer_reviser` 等）；不加环境变量兜底。
- **遥测**：run / tool 遥测经 Facility；公开事件无 PII。

---

## 7. 依赖与排序

```
Phase 2 编辑器 ──► Phase 3 选区/diff（依赖编辑器）
                   │
Phase 4 thread ────┼──► Phase 5 SSE/审批（依赖 thread 与真实事件）──► Phase 6 验收
（可与 3 并行）
```

- 后端可提前并行：Phase 3 revise、Phase 4 threads schema、Phase 5 SSE/审批。
- 前端严格串行：2 → 3；4 可与 3 并行；5 在 4 之后；6 收尾。

---

## 8. 验收策略

- 每增量：`npm run typecheck` + focused 契约测试（`frontend-ux-completion-contract`、`web-shell`、`writer-product-workspace` 及新增）+ `npm run build`；再按依赖跑 broader regression。
- 纯函数单测：diff 应用、thread 排序（`.mjs`，node 原生 TS 直接 import）。
- 后端：Go `go test ./...`、Pi `npm test && typecheck && build`、agent-runtime `pytest`；disposable Postgres live 覆盖 RLS/隔离。
- 最终：fresh browser 视觉验收证据。

---

## 9. 里程碑状态表

| 阶段 | 状态 | 主交付 |
|---|---|---|
| 0 传输底座 | `verified_current` | 增量事件轮询 + 连接横幅 + Idempotency-Key |
| 1 四区布局 | `verified_current` | 三区 + ⌘K + 顶栏 |
| 2 TipTap 编辑器 | `implemented` | 富编辑器 + PE 回退 + 动态加载 |
| 3 选区驱动 + 行内 diff | `implemented` | 选区工具条 + diff + Pi revise |
| 4 持久 thread + 时间线 + chips | `implemented` | threads 表 + 活动时间线 |
| 5 真实 SSE + 审批 + 续传 | `implemented` | held-open SSE + 审批门 |
| 6 视觉打磨 + a11y + 验收 | `implemented` | 打磨 + 契约测试（fresh browser 截图待补） |

---

## 10. 变更记录

- `2026-07-13` 建档。确认编辑器方向为 TipTap（效果最好，PE 回退 + 动态加载）；后端可较大改动。Phase 0/1 已 `verified_current`，Phase 2–6 待开发。
- `2026-07-13` Phase 2–6 主实现落地：TipTap 编辑器、选区/diff、`mode=revise` 契约与 Pi、`0019_writer_threads`、held-open SSE、审批卡、时间线/chips、视觉 CSS 与契约测试。fresh browser 视觉截图仍待真实登录环境。
