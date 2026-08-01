# 功能状态矩阵

状态取值：已完整实现 / 基本实现 / 部分实现 / 只有前端 / 只有后端 / 只有定义 / 未接通 / 疑似废弃 / 无法确认

| 功能 | 前端 | 后端 | Agent | 工具 | 数据库 | 测试 | 当前状态 | 证据 |
|---|---|---|---|---|---|---|---|---|
| 认证/注册/恢复/邀请 | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | apps/api/internal/auth、authrecovery；progress doc 2026-07-31 |
| 项目/工作区/成员 | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | server.go、web workspace |
| 上传（TXT/MD/PDF） | ✅ | ✅ | — | — | ✅(MinIO) | ✅ | 已完整实现 | upload.ts、sourcefiles |
| Seed 流水线（精读/聚合/ontology/角色卡） | ✅ | ✅ | ✅(Python 无工具，JSON chat) | 0 | ✅ | ✅ | 已完整实现 | agent-runtime/temporal/seed.py、global_aggregator |
| Pi Analysis（候选式故事分析） | ✅ | ✅ | ✅(7 工具) | ✅ | ✅ | ✅ | 已完整实现 | analysis_handlers.go、pi-analysis-agent.ts、migration 0020 |
| 资产库/版本/收藏/搜索 | ✅ | ✅ | —(搜索能力由 Writer 工具复用) | — | ✅ | ✅ | 已完整实现 | assets、assetcatalog |
| 混合搜索（keyword/vector/hybrid） | ✅(search-capabilities) | ✅ | — | — | ✅(pgvector) | ✅ | 已完整实现 | apps/api/internal/assets |
| Story Graph 构建/图谱/候选采纳 | ✅(d3-force 画布) | ✅ | ✅(Python graph) | — | ✅ | ✅ | 已完整实现 | storygraph、graph-workspace |
| Worldline 推演（goal→step→canon） | ✅ | ✅ | ✅(Python director + Pi cast) | ✅(cast 5) | ✅ | ✅ | 已完整实现 | worldline.go、pi-worldline-cast-agent.ts |
| 世界线保存路径→Writer 时间线 | ✅ | ✅ | ✅ | — | ✅ | ✅ | 已完整实现 | 0028 migration、loadWorldlineTimeline |
| 角色互动（character console） | ✅ | ✅ | ✅(Python character_dialogue) | — | ✅ | ✅ | 基本实现 | characterconsole |
| Writer run（双阶段：orchestrator+composer） | ✅ | ✅ | ✅(12 工具) | ✅ | ✅ | ✅ | 已完整实现 | 本档案 04/05/07 |
| 检索规划（retrieval planner） | ✅(计划标签) | ✅ | ✅ | — | — | ✅ | 已完整实现 | planRetrieval |
| 常驻规则（always_on） | ✅(常驻徽标) | ✅ | ✅ | — | ✅(0025) | ✅ | 已完整实现 | loadAlwaysOnAssets |
| 一致性检查（canon 矛盾） | ✅(提示卡) | ✅ | ✅ | — | — | ✅ | 已完整实现 | checkConsistency |
| 候选稿采纳 → 正文 | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | writer_draft_adoption.go |
| 修订（revise 模式） | ✅(选中片段) | ✅ | ✅ | — | ✅ | ✅ | 已完整实现 | revise 契约、writer-runs |
| 审校（writer_reviewer） | ✅(审校视图) | ✅ | ✅(Python, 无工具) | — | ✅ | ✅ | 已完整实现 | writer_review.py、review-panel |
| 书籍计划（writer_planning） | ✅ | ✅ | ✅(Python, 无工具) | — | ✅ | ✅ | 基本实现（只产 draft 计划） | writer_planning.py |
| 去重检查 | ✅ | ✅ | ✅(writer_dedup_extractor) | — | ✅ | ✅ | 基本实现（只产 disabled 候选） | dedup.go |
| 手稿导出 | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | manuscriptexport |
| 禁用词/预设 | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | forbidden_lexicon、writer_presets |
| LLM 设置（渠道/模型/绑定/配额） | ✅ | ✅ | — | — | ✅ | ✅ | 已完整实现 | llmadmin、settings-workspace |
| 写作台 SSE 实时流 | — | ✅ | — | — | — | ✅ | 只有后端（前端用轮询） | writeWriterEventsSSEHeldOpen |
| `save_draft_revision` 工具 | — | — | ⛔ | 保留名 | — | — | 疑似废弃（保留名+权限拒绝） | W13 |
| Legacy 数据导入 | — | ✅ | ✅(Python legacy_import) | — | ✅ | ✅ | 部分实现（MAIN-100 未授权） | legacy_import |
| 旧 frontend/（Vue/Vite） | — | — | — | — | — | — | 疑似废弃（已删除，README 声明） | AGENTS.md |
| 多分支 Worldline | — | — | — | — | — | — | 疑似废弃（单世界语义，旧接口不再扩展） | AGENTS.md |
| Pi steer/followUp/RPC/Skill/Extension | — | — | — | — | — | — | 未接通（SDK 能力存在但项目未用） | rg 无结果 |
| 邮件发送（真实 SMTP） | — | ✅ | — | — | ✅ | — | 部分实现（有 notifier+outbox；本地用日志后门；生产需配置） | authrecovery/notifier.go |
| Writer 审批流（writer_approvals） | — | ✅ | — | — | ✅ | — | 只有后端（createWriterApproval 已实现，前端无审批 UI 路径） | postgres-pi-writer-deps.ts createWriterApproval |
| 角色一致性检查工具（前端独立入口） | ✅ | ✅ | ✅ | — | ✅ | ✅ | 已完整实现（由审校/角色面板承载） | characters/character-composer |
| 素材库/素材检索 | ✅ | ✅ | ✅(search_assets 等) | ✅ | ✅ | ✅ | 已完整实现 | assets |
| 伏笔管理（独立 UI） | — | — | — | — | — | — | 未接通：伏笔作为 asset_type/foreshadowing 在搜索/召回中承载，无独立管理页【待确认】 | search_manuscript 注释 |
| Token/费用统计 UI | ✅(billing summary) | ✅ | — | — | ✅ | ✅ | 基本实现 | llm/billing_summary.go |
