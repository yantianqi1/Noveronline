# Book-run Complete Version Design

## Summary

MVP（2026-04-16 已落地）交付了"一键成书 agent 任务"的骨架：book_plan 数据层、book_run 状态机、字数与禁词两重审查、6 个新工具、10 个 API、前端「成书」Tab。本文档规划 **完整版（v2）** 的增量方案，重点补齐**可靠性、质量审查、流水线集成、UX、性能**五个方向的缺口，让 book_run 从"能跑通"升级为"可在真实长期项目中稳定使用"。

## State Check

### MVP 已落地

- `book_plans` 表 + CRUD；`forbidden_lexicon` asset_type 复用现有 assets 表
- `BookRunOrchestrator`：PLAN_INIT → RETRIEVE → OUTLINE → (CHAPTER_WRITE → WORD_AUDIT → LEXICON_AUDIT → COMMIT) × N → DONE
- 6 个新工具 + 5 个新 prompt + 10 个新 API 路由
- 前端：成书计划面板、禁词表管理、SSE 实时进度（阶段条 + 章节表 + 命中日志）
- 15 个工具层单测全部通过

### 关键缺口（v2 全部补齐）

| # | 缺口 | 影响 |
|---|---|---|
| 1 | `run_book` 总从 PLAN_INIT 重启，无断点恢复 | 长任务中断后浪费大量 token |
| 2 | `POST /book-run/abort` 只翻 status，编排器不检查 | 无法真正中止在途任务 |
| 3 | 单章审计失败即整本 break，无跳章策略 | 某章卡死阻塞后续章节 |
| 4 | `plan.preset_id` 存了没用，章节 prompt 未注入 preset | 作者预设风格无效 |
| 5 | `reviewer_prompt.py` 的 6 维度质量审查从未接入 | 只有字数/禁词硬审，无质量审 |
| 6 | OUTLINE 一次定稿，无中途修改通道 | 后章不能吸取前章教训 |
| 7 | book_run 结束后不自动同步世界数据 | 新角色/伏笔不进入档案 |
| 8 | 审计操作不可追溯、不可撤销 | 作者对改写结果只能整块接受或整块拒绝 |
| 9 | token / 耗时无计量 | 无法预估剩余任务成本 |
| 10 | 无 mock LLM 的集成测试 | 状态机改动只能手工验证 |
| 11 | style_extractor 的"禁用句式"字段不会自动回灌 forbidden_lexicon | 禁词表需纯手工维护 |
| 12 | 多章节串行执行，独立章节无法并发 | 书级任务耗时线性叠加 |

---

## Enhancements — by priority band

### Band 1 · Reliability & control（必做）

#### 1.1 断点恢复

**修改文件**：`book_run_orchestrator.py`、`book_plan_service.py`、`api_fastapi/writer_agent.py`

`BookRunOrchestrator.run(plan_id)` 启动时读取 `plan.last_stage` 与 `plan.current_chapter_order`，按以下规则跳转：

```
IF plan.status in ("completed", "aborted"):
    yield error "plan 已终态，请新建或复制后再跑"
ELIF plan.last_stage == "PLAN_INIT" 或空:
    从 PLAN_INIT 开始（冷启动）
ELIF plan.last_stage == "RETRIEVE":
    复用 plan.retrieval_summary，跳过 RETRIEVE 直接进 OUTLINE
ELIF plan.last_stage == "OUTLINE":
    复用已落库的 outline_version_ids[-1] 对应的大纲，直接进 CHAPTER_WRITE
ELIF plan.last_stage.startswith("CHAPTER_WRITE#N"):
    从第 N 章 CHAPTER_WRITE 重做（可能上次写到一半）
ELIF plan.last_stage.startswith("WORD_AUDIT#N") / "LEXICON_AUDIT#N":
    从第 N 章对应审计阶段重做
ELIF plan.last_stage.startswith("CHAPTER_COMMIT#N"):
    从第 N+1 章开始
```

**关键点**：
- 每次 `set_status(plan_id, ..., last_stage=...)` 需**先落盘再推进**，不能在阶段结束后才记
- `CHAPTER_WRITE` 重跑前要清空本章已有 `manuscript_block`（asset_type='manuscript_block' 且 chapter_id 匹配），避免重复落库。新增 `adapter.clear_chapter_blocks(chapter_id)` 方法
- 新增 API `POST /book-run/resume`（body: `{plan_id}`），前端按钮"从断点继续"

**兼容性**：MVP 既有的 `POST /book-run` 保持冷启动语义；恢复走新端点，语义清晰。

#### 1.2 Cooperative Abort

**修改文件**：`book_run_orchestrator.py`、`agent_loop.py`

当前 `/book-run/abort` 只设 `status=aborted`，但 orchestrator 在 `async for chapter in range(...)` 里不检查。

方案：
- 在外层章节循环每次迭代开头重查 `plan = self.plan_service.get_plan(plan_id)`，若 `status == "aborted"` 则退出
- 在内层 audit 循环每轮 `AgentLoop.run` **之前**同样检查
- 不侵入 `AgentLoop` 本身（AgentLoop 的 tool_calls 不应被打断以免损坏 DB 状态）

粒度：章节级 + 审计轮级，最坏延迟 ≈ 1 个 LLM 调用。够用。

**SSE 事件**：新增 `{"type": "book_run_aborted", "stage": ..., "chapter_order": ...}`。

#### 1.3 跳章策略

**修改文件**：`book_plans` 表、`book_plan_service.py`、`book_run_orchestrator.py`

`book_plans` 新增字段 `on_chapter_failure TEXT DEFAULT 'abort'`，取值 `abort|skip|retry_once`。

外层循环 `except Exception` 分支按策略决定：
```
abort:       记录 error_log，break 外层
skip:        记录 error_log，continue 下一章（本章标 failed）
retry_once:  本次循环重试本章 1 次，仍失败则等价 abort
```

前端在「成书计划」面板加 `Select`：`章节失败时 [终止 / 跳过 / 重试一次]`。

`chapter_content.status` 新增枚举值 `failed`，前端稿件 TOC 按钮上用红色边框标识。

#### 1.4 Preset 接入章节写作

**修改文件**：`book_run_orchestrator.py`、`prompts.py::build_chapter_writer_prompt`

在 `run()` 中读取 `plan.preset_id` → `PresetRepository.list_presets(project_id)` 过滤 → 把 `preset.system_prompt` 作为 `preset_prompt` 参数传给 `build_chapter_writer_prompt`，prompt 在 base 段落前拼接：

```
{preset_prompt}

---

你是小说写作 agent 的「单章执笔」。...
```

若无 preset_id 或未命中，走现有默认兜底（沿用 orchestrator._load_preset 的 fallback 文案）。

**测试覆盖**：单元测试验证 preset.system_prompt 被拼进 system prompt。

#### 1.5 Mock LLM 的集成测试

**新增**：`backend/tests/test_book_run_orchestrator_flow.py`

使用一个 `FakeAsyncLLMClient`（实现 `chat_with_tools(...)` 方法），按脚本依次返回：
- RETRIEVE 阶段：无 tool_calls，返回"全书摘要..."文本
- OUTLINE 阶段：返回 ```json [...]``` 大纲
- CHAPTER_WRITE×N 阶段：每章返回 ```chapter 段落 ``` + `SUMMARY: xxx`
- WORD_AUDIT 阶段：第一次返回 `get_chapter_word_stats` 调用；第二次返回 `splice_block` 调用；第三次返回 `{"verdict":"pass"}`
- LEXICON_AUDIT 阶段：若脚本扫无命中自动跳过；否则类似流程

断言：
- SSE 事件序列完整（PLAN_INIT → RETRIEVE → OUTLINE → (CHAPTER_WRITE → WORD_AUDIT → LEXICON_AUDIT → CHAPTER_COMMIT) × N → book_run_done）
- `book_plans.status` 演进 draft → writing → completed
- `chapter_content.status` 各章为 `completed`
- `plan.chapter_ids` 长度 = chapter_count

用 `unittest.mock.patch` 替换 `LlmRouter.build_async_client`。测试不碰真实 LLM，0 token 消耗。

### Band 2 · 质量审查

#### 2.1 第三重审查：QUALITY_AUDIT

**新增文件**：`prompts.py` 加 `build_quality_audit_prompt`；`book_run_orchestrator.py` 加 QUALITY_AUDIT 阶段

复用 `reviewer_prompt.py::REVIEWER_SYSTEM_PROMPT`（6 维度：连续性、角色一致性、悬念、风格、描写质量、叙事节奏），但作为**诊断 + 修复 loop**，不再只输出 issues。

流程：
```
QUALITY_AUDIT（在 LEXICON_AUDIT 之后、CHAPTER_COMMIT 之前）
  ↓
  1) agent 读完整章正文（get_manuscript_context 或 query_scene）
  2) agent 输出 issues JSON（若每项 severity 都 <= "minor" 或 pass，跳出）
  3) 否则对每条 high-severity issue，调 rewrite_span 或 splice_block 修复
  4) 复查；最多 4 轮
  5) 仍失败 → 走 plan.on_chapter_failure 策略
```

工具白名单：`{get_manuscript_context, query_scene, rewrite_span, splice_block, get_chapter_word_stats}`。

**用户开关**：plan 新增字段 `quality_audit_level TEXT DEFAULT 'off'`，取值 `off|standard|strict`。
- off：不跑（MVP 行为）
- standard：只修复 high-severity
- strict：所有 severity 都修

#### 2.2 Outline 中途修正

**新增工具**：`amend_chapter_outline`（写工具）
- 入参：`chapter_order, new_outline_entries, reason`
- 行为：更新 `chapter_meta.outline_json`，同时保存新版本到 `outline_versions`

**使用范围**：只在每章 CHAPTER_COMMIT 后的"章末反思"小 loop 中暴露。新增阶段 OUTLINE_REFLECT（紧接 COMMIT）：
- 让 agent 看本章摘要 + 后续章节大纲，判断后续章节是否需要调整
- 允许 agent 对**尚未写的**章节调用 `amend_chapter_outline`
- 不允许回改已完成章节（前向一致性保护）

此阶段 LLM 温度低、max_tokens 小，通常 1 轮完成。节省大量 token 相比"每章都重跑大纲"。

**开关**：plan 新增字段 `outline_reflection_enabled INT DEFAULT 0`。

#### 2.3 Style asset → forbidden_lexicon 自动提取

**修改文件**：`services/assets/style_extractor/aggregator.py`、新增 `services/writer_agent/lexicon_sync_service.py`

`style_extractor` 已有 `writing_style` asset，其 `payload.sentence_features` 常隐含"避免 XX 句式"信息。扩展其 schema 显式加字段：
```json
{
  ...,
  "forbidden_patterns": [
    {"pattern": "突然", "match_type": "literal", "note": "避免突然类副词堆砌"},
    {"pattern": "不禁", "match_type": "literal", "note": "风格禁用"}
  ]
}
```

新增 `LexiconSyncService.sync_from_style_asset(style_asset_id)`：
- 读 style_asset.payload.forbidden_patterns
- 找或新建配套的 forbidden_lexicon asset（title = `"自动｜<风格标题>"`）
- 全量覆盖其 entries

前端「禁词面板」加"从文风 asset 同步"按钮，列出可选的 writing_style asset，勾选后调 sync。

此外 book_plan 增加字段 `auto_sync_style_lexicons INT DEFAULT 0`，若开启则在 PLAN_INIT 阶段对所选 `style_asset_ids` 逐个 sync 并把生成的 forbidden_lexicon asset 追加到 `plan.forbidden_lexicon_asset_ids`。

### Band 3 · 流水线集成

#### 3.1 DONE 阶段自动 world-update

**修改文件**：`book_run_orchestrator.py`

在 `status=completed` 之前、`book_run_done` 事件之前，新增阶段 WORLD_SYNC：
```python
if plan.world_sync_enabled:
    yield {"type": "book_run_stage", "stage": "WORLD_SYNC", ...}
    for chapter_id in completed:
        content = chapter_repo.get_chapter(project_id, chapter_id, include_content=True)["content"]
        # 复用 existing build_world_update_prompt + AgentLoop 逻辑
        async for ev in _run_world_update(project_id, chapter_id, content):
            yield ev
```

但一本书 N 章调 N 次 world-update 太贵。优化：
- 把全书所有新章节拼成 1 份合并文本（每章前加 `# 第 X 章 · <title>`）
- 调一次 world-update；prompt 里说明"这是批量输入，请去重后写库"
- 工具里的 manage_* 都自带去重（先查再写），所以天然幂等

新增 `plan.world_sync_enabled INT DEFAULT 1`。

#### 3.2 书级摘要 + 章节关系演化

**新增 API 端点**：`POST /book-run/summarize`（body: `{plan_id}`）

不随 book_run 自动触发（成本敏感），做成显式按钮。
- 读全书正文（拼接）
- 单次 LLM 调用（无工具），返回：
  ```json
  {
    "overall_summary": "200 字本卷梗概",
    "arc_progression": "本卷推进了哪些叙事弧线",
    "new_threads": ["新开悬念 1"],
    "resolved_threads": ["解决的悬念 1"],
    "key_relationship_shifts": [{"pair": "A↔B", "change": "...从敌对变同盟..."}]
  }
  ```
- 存到 `volume_summaries` 表（已存在）或 plan.payload_json 的新字段 `final_summary_json`

前端「成书」Tab 显示"查看本书摘要"按钮。

### Band 4 · UX

#### 4.1 章节写作流式渲染

**问题**：当前 CHAPTER_WRITE 用 `AgentLoop`，只在最终 `brief_ready` 才拿到完整章节正文 —— 前端看不到增长。

**方案**：在 CHAPTER_WRITE 阶段，工具轮次结束、LLM 进入"产出正文"的最后一轮时，**切换到流式通道**。
- AgentLoop 保留为"工具调用阶段"（检索、planning）
- 当 LLM 某轮不返回 tool_calls 时，立即在 `book_run_orchestrator` 里用 `WriterComposer.compose_stream` 做二次流式生成（输入是 AgentLoop 消息历史 + 流式生成指令）
- 前端收到 `writer_token` 事件逐字渲染

**权衡**：复杂度 vs 用户体验。做 Band 4 优先这个。

#### 4.2 审计操作日志 + 撤销

**新表**：`audit_actions`
```
action_id TEXT PK
plan_id TEXT NOT NULL
chapter_id TEXT
chapter_order INT
kind TEXT           -- word | lexicon | quality
tool_name TEXT      -- splice_block | rewrite_span
input_json TEXT     -- 工具调用原始参数
before_snapshot TEXT -- 受影响块的快照
after_snapshot TEXT  -- 写入后的快照
reason TEXT
created_at TEXT
```

`_splice_block` 和 `_rewrite_span` 执行前读 block 内容存入 `before_snapshot`；执行后存 `after_snapshot`。两者写到 `audit_actions`。

**API**：
- `GET /book-run/{plan_id}/audit-actions?chapter_id=xxx`
- `POST /book-run/audit-actions/{action_id}/revert`（把 after 还原为 before）

**前端**：「成书」Tab 章节行后加"审计记录"抽屉，逐条列操作 + 撤销按钮。

#### 4.3 Token 预算仪表盘

**book_plans 新增**：
```
token_usage_json TEXT DEFAULT '{}'   -- {retrieve: 0, outline: 0, chapter_write: {...}, word_audit: {...}, ...}
```

`BookRunOrchestrator` 每次 `AgentLoop.run()` 结束取 `loop.total_usage`，按阶段累加写回 plan。

前端成书 Tab 显示总 token、按阶段饼图。开 book_run 前可提示"估计消耗 X token"（以每 1000 字 ≈ 1500 prompt + 800 completion 简单估）。

#### 4.4 禁词表 CSV 导入/导出

**API**：
- `POST /forbidden-lexicons/{asset_id}/import-csv`（multipart form-data 上传 CSV）
- `GET /forbidden-lexicons/{asset_id}/export-csv`

CSV 列：`pattern,match_type,category,severity,note,whitelist_contexts`（后者分号分隔）。

前端面板加两个按钮。

#### 4.5 章节 diff 预览

写作阶段：agent 初稿（`_chapter_write_result.prose`）落到临时字段 `chapter_meta.draft_initial_json`（新增）。审计阶段执行 `splice_block` / `rewrite_span` 后，章节当前正文作为"最终稿"。

前端章节行加"对比查看"按钮，打开一个 split view：左初稿、右最终稿、行级 diff 高亮。

用现成的 `diff-match-patch` 或 `jsdiff` 库做前端 diff。

### Band 5 · 性能

#### 5.1 并发章节生成（谨慎）

前提：章节之间**无强上下文依赖**（某类非线性叙事可能需要）。

**plan 新增**：`concurrent_chapter_limit INT DEFAULT 1`（默认串行）。

实现：`asyncio.gather` 并发多个 `_run_chapter_write` + 对应两重审计 loop，上限由字段控制。

**风险**：
- SQLite WAL 并发写入有限；写工具已串行但并发多个 agent_loop 可能仍压垮连接池
- LLM 并发调用 token rate limit
- 前章摘要注入后章的机制在并发时需改为"拿到谁的就用谁的"

所以默认 `concurrent_chapter_limit=1`；开到 2-3 需要用户显式设置。

MVP 之后再实施，且需要加单独的 rate-limit 保护。

---

## Cross-cutting concerns

### 1. 数据迁移（向后兼容）

所有 `book_plans` 新字段（`on_chapter_failure`、`quality_audit_level`、`outline_reflection_enabled`、`world_sync_enabled`、`auto_sync_style_lexicons`、`token_usage_json`、`concurrent_chapter_limit`）都带 `DEFAULT` 值，SQLite `ALTER TABLE ... ADD COLUMN` 可以就地加。不做一次性大迁移；按功能上线逐次加列。

新表 `audit_actions` 由 `metadata.create_all` 自动建。

### 2. 工具白名单管理

当前 `book_run_orchestrator.py` 硬编码了 `_READ_TOOL_NAMES` / `_WORD_AUDIT_TOOL_NAMES` / `_LEXICON_AUDIT_TOOL_NAMES` 三个 set。v2 加入 QUALITY_AUDIT + OUTLINE_REFLECT 后会有 5+ 个 set，易漂移。

**重构**：引入 `tool_whitelists.py`，每个阶段一个常量 + `get_tools_for_stage(stage) -> List[Dict]` 函数。单点维护。

### 3. 状态机可视化

阶段越多，用户越容易迷失在"现在在哪一步"。补充前端阶段条显示逻辑：
- 章节循环内的阶段（CHAPTER_WRITE / WORD_AUDIT / LEXICON_AUDIT / QUALITY_AUDIT / OUTLINE_REFLECT / CHAPTER_COMMIT）聚合为"第 N 章"一格，点击展开子阶段
- 全书级阶段（PLAN_INIT / RETRIEVE / OUTLINE / WORLD_SYNC / DONE）单独一格

### 4. 错误恢复的事务语义

- OUTLINE 生成后、章节循环开始前若崩溃：大纲已落库，next run 从 CHAPTER_WRITE 继续 ✓
- CHAPTER_WRITE 写到一半崩溃：已落的 manuscript_block 保留。next run 从 CHAPTER_WRITE 重做前需 `clear_chapter_blocks` 避免拼接重复
- WORD_AUDIT 中某次 splice_block 失败：当前章块状态不明，需让 LLM 自己拿 stats 看当前状态（工具调用本身是幂等的）

### 5. 可观测性

所有阶段 enter/exit 日志 + duration + token 都写到现有的 `llm_activity_tracker`。用户可在 LLM 设施面板看到每次 book_run 的详单。

book_plans 加 `started_at`、`finished_at` 字段支持跨日查询。

---

## Landing order

分三次迭代交付，每次完成后可用：

### Iteration 1（核心可用性，1-2 天工作量）

目标：任何中断都能恢复，abort 真正起效，preset 生效，有集成测试。

1. B1.2 cooperative abort（最小侵入）
2. B1.4 preset 接入 chapter writer
3. B1.1 断点恢复 + `POST /book-run/resume`
4. B1.3 跳章策略
5. B1.5 mock LLM 集成测试

### Iteration 2（质量 + 流水线，2-3 天）

目标：book_run 输出质量接近人工精修，自动维护世界数据与禁词表。

6. B2.1 QUALITY_AUDIT 阶段
7. B3.1 DONE 后自动 WORLD_SYNC
8. B2.2 OUTLINE_REFLECT
9. B2.3 style → lexicon 自动同步
10. B3.2 书级摘要端点

### Iteration 3（UX + 性能，2-3 天）

目标：作者深度参与过程，任务成本可预估可控。

11. B4.3 token 预算仪表盘（数据层简单，UI 即可见）
12. B4.2 审计操作日志 + 撤销（新表 + UI 抽屉）
13. B4.1 章节写作流式渲染（重构较大）
14. B4.4 CSV 导入/导出
15. B4.5 章节 diff 预览
16. B5.1 并发章节（需要限流保护）

---

## Out of scope（不在 v2，后续讨论）

- **人机协作编辑模式**：用户在 audit 阶段直接介入修改某块，agent 依此继续。需要一个协作编辑协议和断点/锁机制，超出 v2 范围。
- **多本书级别的"系列"管理**：book_plan 之上再抽一层 series，跨卷设定一致性。等单本流程稳定再做。
- **Reviewer 6 维度的评分报告可视化**：质量审查修复行为 v2 会做，但展示每次修复涉及哪些维度的仪表盘留给 v3。
- **大纲从外部 markdown / Excel 导入**：可以用现成 assets 库的 ingestion_agent 间接做到，不重复造轮子。
- **多 LLM 模型混用**：如让弱模型做字数扩写、强模型做质量审。需要 LLM Router 支持按阶段绑定不同模型。留 v3。

---

## Verification

每个 iteration 完成后运行：
1. 全套 `pytest tests/test_book_run_*`
2. 前端 `npm run build`
3. 端到端手测：3 章 × 1500 字 + 质量审查 + 禁词表 + 中途 abort 一次 + resume，验证落库数据一致

最终全量验证：5 章 × 3000 字，模拟真实创作负载。
