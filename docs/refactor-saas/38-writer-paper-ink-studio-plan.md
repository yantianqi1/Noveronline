# 38. 写作台「纸墨书房」开发方案

更新时间：`2026-07-22`
状态：**方案已定，待开工**。高保真原型见 `apps/web/public/writer-prototype.html`。

> 本文是写作台（Writer Workbench）的唯一开发方案。后续实现、验收、任务拆解都以本文为准；
> 是否已完成仍以 `24-current-development-progress.md` 与当前 worktree 为准，不以本文推断进度。

---

## 0. 一页速览

| 项 | 结论 |
|---|---|
| 目标形态 | **对话是唯一入口，产物是唯一主角，过程折叠成一行。**（doc 36 定死的 IA，本文推进落地） |
| 视觉语言 | 延续全站「纸感朱砂」：暖纸底 + 手稿白面宋体 + 朱砂唯一主操作 + 旧金只做候选态 |
| 布局 | 一个路由两种状态：**起点态（Home）** ⇄ **任务态（Task，左对话 360px + 右产物画布）** |
| 核心安全契约 | Agent 只产**候选稿**；进正式手稿必须作者**显式采用**。失败显示真实作者化原因，不假装成功 |
| 后端 | Writer API 已摸清（见 §6 契约摘要），链路完整可用；PI writer worker 实跑通性**未验证**（W0 探明） |
| 不做 | 旧 `writer-studio-grid`、四 tab、左结构轨、深色 agent rail、折叠 composer、mock 假后端页 |

---

## 1. 设计哲学：三层心智

任何 UI 元素必须归入其中一层，否则不该出现：

| 层 | 内容 | 可见性 |
|---|---|---|
| **对话层（入口）** | composer、消息、示例任务、任务状态行 | 常驻，视觉次于产物 |
| **产物层（主角）** | 手稿、候选稿、审校报告、大纲/计划、导出文件 | 主区域最大化 |
| **过程层（按需）** | Agent 检索/工具/思考、trace、原始事件 | 默认折叠为一行状态，逐级展开 |

写作台 = 「你和一位常驻合著者，围着一张稿子工作」。界面像编辑部案头，不像调试面板。

---

## 2. 页面形态：一个路由，两种状态

不用「布局」区分功能，用「状态」区分——这是「简单」的关键。

### 2.1 起点态（Home）
触发：项目无进行中任务，或点「新任务」。
元素只有四样：一句价值说明、居中大 composer、3–4 个示例任务、最近产物/章节入口。**无 readiness 面板**——LLM 门控后置到首次真正调用时。

### 2.2 任务态（Task）
触发：发出指令，或打开既有章节。
- **左 · 对话 rail（~360px）**：用户消息（朱砂气泡 + @引用 chip）、任务状态行、Agent 摘要回复、产物摘要卡；底部常驻 composer。
- **右 · 产物画布（主导）**：标题栏（章节切换器 ▾ · 字数 · 保存状态 · ⌘K · ⋯）+ 按产物类型切换的渲染器 + 完成后浮出的操作条。

两态同路由迁移：composer 从页面中央「落位」到左栏底部，形成「我说的话变成了正在推进的任务」的连续感。

---

## 3. 六个核心组件

1. **任务状态行（WriterTaskStatusLine）**——每个任务一行可展开小字，实时更新不刷屏。折叠态永远中文、无 UUID/工具名/英文枚举：
   `⏳ 正在理解要求` → `🔍 正在查阅资料 · 已完成 N 项` → `✍ 正在起草正文 · N 字` → `✓ 已完成 · 生成候选稿 N 字` / `⚠ 未完成 · <作者化原因> [重试]`。
   展开第一层=作者化步骤列表；第二层（trace/原始事件）藏 `[⋯]` 授权抽屉，普通作者不可见。
2. **产物画布（WriterArtifactCanvas）**——按产物类型换渲染器：正式手稿（沉浸阅读+就地编辑）、候选稿（流式打字机 + 虚线框 + 角标）、审校报告（issue 卡片）、大纲/书籍计划（文档卡）、导出（下载卡）。
3. **常驻 Composer**——自动增高输入框 + `@`引用（搜索选择器，替代旧三列勾选）+ 意图 chip（可选，默认自动识别）。
4. **章节切换器**——画布标题栏 `《书名》› 第 N 章 ▾`，点开章节/场景树 + 新建。取代左结构轨 + structure tab。
5. **命令面板 ⌘K**——跳章节、开审校、导出、大纲、去重、禁用词等低频动作统一入口。
6. **审批卡（WriterApprovalCard）**——Agent 动正史/正文前醒目卡片 `[同意]/[拒绝]`，阻塞时状态行「等待你的确认」。

---

## 4. 画布渲染器 × 操作条

| 产物 | 画布形态 | 操作条 |
|---|---|---|
| 候选稿 | 流式正文 + 虚线边框 + 「候选稿」角标 | 采用为手稿 · 继续修改 · 复制 · 丢弃 |
| 正式手稿 | 沉浸编辑（一期受控 textarea → 目标 TipTap），选区浮「请 Agent 改这段」 | 保存状态 · 版本 · 导出 |
| 修订建议 | 内联 diff | 接受 · 保留原文 · 比较两版 |
| 审校报告 | issue 卡片列表，逐条定位正文 | 接受 · 忽略 · 全部处理 |
| 大纲/书籍计划 | 结构化文档卡 | 编辑 · 应用为章节结构 |
| 导出文件 | 下载卡（文件名/大小/格式） | 下载 · 重新生成 |

规则：**产物永远在画布，对话流只放摘要卡**，点卡片即切画布到该产物。视觉优先级：产物 > 对话 > 状态行 > 技术细节。

---

## 5. 视觉系统（延续全站令牌）

- 手稿纸 `#fffdf8` 白面承载正文（宋体、行高 1.9、居中 max-width ~680px、近无圆角），保证阅读沉浸。
- 朱砂 `#8f211b`：唯一主操作（发送/采用）+ 选中态，不泛滥。
- 旧金 `#a9854f`：候选稿虚线框/角标/分隔，唯一语义。
- 深墨 `#171a1b`：仅选区浮条、技术抽屉等沉浸对象，不与纸面平铺多个深色中心。
- 每屏一个主操作；长任务按钮都有 disabled/loading/error；destructive 必确认；空态必给下一步。
- 动效 160/220/280ms 三档、自然减速曲线，只动 transform/opacity/color；`prefers-reduced-motion` 下关闭非必要动画。
- 移动端 <960px 收成「对话 ⇄ 产物」两态切换，主操作 ≥44px，正文 ≥16px。

---

## 6. 后端契约摘要（已调研锁定，详见调研报告）

- **Writer run**：`POST /v1/projects/{id}/writer-runs`（`{mode, instruction, chapter_id?, scene_id?, options?}` → 202 `{run_id, trace_id, mode, instruction, status:"queued"}`）；`GET /v1/writer-runs/{runId}`；`POST /v1/writer-runs/{runId}/cancel`。
- **事件流**：`GET /v1/writer-runs/{runId}/events` —— `Accept: text/event-stream` 给 SSE（活跃 run 长连，终态一次性 dump，靠 `Last-Event-ID`/`after_event_id` 续传）；默认 JSON `{items:[WriterEvent]}` 可轮询。
  - **W0 实测锁定（2026-07-22）**：JSON 模式**每页固定 100 条**，envelope **只有 `items`，无 `cursor`/`has_more`**。客户端必须自记最后一条 `event_id`，循环带 `?after_event_id=<last_id>` 拉取，直到返回 **<100 条** 即到底。一次 draft run 可达 200+ 条事件，不追游标会在第 100 条处**静默截断正文**。W2 接事件流必须内置此追游标循环。
  - 事件类型：`writer.run.started` / `writer.tool.started|completed` / `writer.token{token,chunk_index}` / `writer.draft.saved{draft_id}` / `writer.revision.proposed` / `writer.approval.required|resolved` / `writer.run.completed|failed|cancelled`。
  - payload 已被服务端脱敏；`writer.token` 保留 `token`。
  - **W0 已验证**：PI writer worker（pi-agent-runtime `PiWriterRunWorkflow`，task queue `writer-streaming`）在本环境跑通——模块绑定（7 个 `writer_*` 全绑 `gpt-5.5`）、orchestrator 工具循环、token 流、`draft.saved`+`run.completed` 收尾全部正常。
- **草稿**：`POST /v1/drafts/{id}/adoptions`（显式采用进手稿）；`POST/GET /v1/drafts/{id}/reviews`（审校）；`PATCH /v1/draft-review-issues/{issueId}`（issue 处置）。
  - **W2 实测锁定（2026-07-23）**：adoption body `{chapter_id, block_order}`。**`block_order` 传 `0`**——后端取 `MAX(block_order)+1` 自动追加。`block_order` 在**全项目 active blocks 范围唯一**（`idx_manuscript_blocks_active_order`），传一个已占用的具体值会撞唯一索引 → 503 `DRAFT_ADOPTION_WRITE_FAILED`。前端采用时永远传 0。
  - adoption 响应（202）：`{draft_id, block_id, project_id, status:"adopted", chapter_id, block_order}`。候选稿 `status` 从 `candidate` → `adopted`，同时新建一个 `manuscript_block`（`source_draft_id` 回指 draft）。
- **持久对话**：`GET/POST /v1/projects/{id}/writer-threads`；`GET/POST .../{threadId}/messages`；`POST /v1/projects/{id}/writer-approvals/{approvalId}/decision`。
- **结构**：`GET/POST /v1/projects/{id}/chapters`（+reorder）、`/v1/chapters/{id}`（PATCH/DELETE/versions/scenes）、`/v1/scenes/{id}`、outlines、book-plans（+generations）、writer-presets、forbidden-lexicon。
- **手稿工作区**：`/v1/projects/{id}/manuscript-workspace/blocks`（全 CRUD/reorder/move/tags/versions/restore）、`commands`（一键动作）、`exports`、`dedup-extractions`、`dedup-patterns`（accept/reject）。
- **手稿导出**：`/v1/projects/{id}/manuscript/exports/{exportId}/download`（真实文件流）。
- 多写操作需 `expected_version`（乐观锁）；启动类操作吃 `X-Request-Id`（幂等）。
- **未配置后端**统一 503 + code（如 `WORKFLOW_BACKEND_UNCONFIGURED`），前端必须显式呈现，不静默降级。

**BFF 约定**：浏览器只连同源 Next Route Handler；服务端转发 session cookie、注入 CSRF、代签 proof、透传 `X-Tenant-Id`。run 级路由注意顶层 `/v1/writer-runs/...` 与 `/v1/drafts/...`（不在 `/v1/projects/` 前缀下）。

---

## 7. 波次切分（按价值排序，逐块可验收）

| 波次 | 内容 | 出口标准（真实后端验收） |
|---|---|---|
| **W0 探路** | 实发一个 writer run，验证 PI writer worker 在本环境能否跑通（模块绑定/工具调用/token 流） | 拿到真实 `writer.token` 流 or 明确失败原因并修复 |
| **W1 画布 + 手稿** | 章节切换器、手稿读取/编辑/保存、字数/保存状态、BFF 代理 chapters + manuscript-workspace | 能读章节、编辑正文、保存成功、刷新还在 |
| **W2 对话 + PI 接入** | 持久 thread、composer、writer run 启动、任务状态行聚合事件、SSE/轮询 token 流进候选稿、显式采用 | 说一句话→看到 PI 真写的稿流出→采用进手稿 |
| **W3 起点态 + 结构管理** | 零教程首屏、章节/场景 CRUD+reorder、新建章节 | 空项目零障碍开写、结构可管理 |
| **W4 写作辅助** | 审校报告（issues 处置）、大纲/书籍计划、导出手稿、选区改写 | 能跑审校/出大纲/导出真实文件 |
| **W5 收口** | ⌘K 命令面板、审批流、技术详情抽屉、一键命令、禁用词/去重、移动端 | 强大功能全可达、移动端可用、技术细节权限内可见 |

每个波次：focused tests 先行 → 实现 → 真实后端端到端验证（连 127.0.0.1:3888，compose 拉起）→ 浏览器实测截图存证。

---

## 8. 验收清单（终态）

- 能创建章节/场景并管理结构。
- 能发 writer run，候选稿真实流式出现，能看到检索工具活动（折叠为一行）。
- 失败显示真实作者化原因 + 重试，不假装成功。
- 能显式采用候选稿进手稿，正文字不被静默覆盖。
- 能就地编辑手稿并保存，刷新恢复。
- 能跑审校、处置 issue；能出大纲/书籍计划；能导出真实手稿文件。
- 技术 trace 仅授权角色在抽屉可见；普通作者界面无 UUID/原始 JSON/内部错误码。
- 桌面双栏、移动两态，无横向滚动；LLM 未绑定时给明确配置入口。

---

## 9. 明确不做

- 旧 `writer-studio-grid`、深色 `writer-agent-rail`、折叠 composer、四 tab、左结构轨。
- stub/mock 假后端的演示页；写死领域数据。
- 多分支 worldline 对比、社交媒体/舆情语义。
- 把 trace/技术面板堆进主 IA。
