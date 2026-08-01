# 数据、状态与持久化

## 1. 数据库与 ORM

- Postgres 16 + pgvector（`infra/docker-compose.yml`），31 个 migration（`infra/postgres/migrations/0001~0031`）。
- Go：pgx/v5 手写参数化 SQL + RLS 事务 helper（`app_set_tenant_context`）；无 ORM。
- Pi：node-postgres（pg）手写 SQL，同样强制 tenant 上下文（postgres-pi-writer-deps.ts `createPgPoolQueryExecutor`）。
- Python：psycopg3 手写 SQL。

## 2. 核心数据模型（按域）

| 域 | 表 | 说明 |
|---|---|---|
| 身份 | tenants、users(部分)、tenant_memberships、project_members、workspace_membership_scope_backfill_audit | 多租户 |
| 项目 | projects、project_readiness_snapshots、source_files、text_segments | 项目+上传分段 |
| 写作结构 | chapters、scenes、book_plans、outline_versions、chapter_versions、scene_versions | 结构+版本 |
| 正文 | manuscript_blocks、manuscript_block_versions、manuscript_block_embeddings、writer_drafts | 正文块=最终事实；draft=候选 |
| Run/事件 | writer_runs、writer_threads、writer_thread_messages、writer_approvals、workflow_runs、workflow_events、analysis_runs、analysis_workspace_files、analysis_candidates、seed_* | 任务+事件流 |
| 知识 | assets、asset_versions、asset_embeddings、asset_links、asset_collections、asset_candidate_proposals、entities、entity_aliases、entity_evidence、relationships、world_rule_evidence、story_graph_*、narrative_arcs、plot_threads、world_events、character_events | 图谱/资产 |
| Worldline | worldline_sessions、worldline_events、worldline_variables、worldline_preparations、worldline_prepared_agents、worldline_saved_paths、worldline_goal_starts、worldline_event_adoptions | 推演 |
| LLM | llm_channels（含 encrypted_api_key）、llm_models、llm_module_bindings、llm_platform_module_defaults、llm_quota_policies、llm_quota_reservations、llm_activity、usage_events、resource_locks | 设施 |
| 可观测 | agent_traces、agent_trace_events、audit_logs、auth_security_audit_logs | trace/审计 |
| 写作工具 | manuscript_exports、writer_dedup_patterns、writer_presets、forbidden_lexicon_entries、draft_reviews、draft_review_issues、manuscript_asset_distillation_requests | 工具 |
| 协作 | collaboration_invitations、collaboration_delivery_attempts、password_reset_* | 邀请/恢复 |

## 3. 哪些是真实业务事实，哪些只是记录

| 类别 | 内容 |
|---|---|
| 业务事实（authoritative） | projects、chapters、scenes、manuscript_blocks（adopted 正文）、assets(lifecycle=canon/seed/material)、entities、worldline_events(status=canon)、world_rules |
| 候选（非事实，需用户动作） | writer_drafts(status=candidate)、analysis_candidates、asset_candidate_proposals、worldline_events(status=candidate)、assets(lifecycle=candidate) |
| 聊天/记录 | writer_thread_messages、workflow_events、llm_activity、usage_events、agent_traces |
| 仅内存 | Pi Agent 实例、Temporal 阶段 checkpoint（heartbeat details）、Go TemporalWriterStarter.runs map（进程内缓存 run 记录，仅辅助） |

## 4. 持久化与重启

| 内容 | 重启后 |
|---|---|
| 全部业务表/事件/线程/草稿 | ✅ 保留（Postgres） |
| 上传文件/导出 | ✅ 保留（MinIO + DB 元数据） |
| 运行中的 Temporal workflow | ✅ 保留并可恢复（Temporal 持久化；活动 checkpoint 跳过已完成阶段） |
| Pi Agent 内存状态 | ❌ 丢失（每次 run 重新创建，无会话状态） |
| Go 进程内 runs map | ❌ 丢失（只用于快速 GetWriterRun；DB 是真相源，读不到时回退 DB） |
| 前端状态 | ❌ 丢失（从 DB 线程+事件重建） |

## 5. Session 与数据库记录的关联

- 没有「AgentSession 持久化」；对应物是 `writer_runs.run_id`（每个用户请求 = 一个 run）。线程（writer_threads）通过 `writer_thread_messages.run_id` 关联 run；run 通过 `workflow_run_id` 关联 workflow_runs；workflow_events 通过 run_id + sequence 排序。
- 事件还原链路：`workflow_events`（runtime_event_key 幂等）→ Go 读侧 sanitize → 前端 reducer。

## 6. 状态同步与一致性风险

| 风险点 | 现状 | 证据 |
|---|---|---|
| 正文已保存但状态未更新 | 保存失败 → 活动抛 WRITER_DRAFT_SAVE_FAILED → run failed；状态更新失败 → 活动 throw（updateWriterRunStatus 双表更新校验 writer_updated/workflow_updated ≥1） | pi-writer-activities.ts |
| 半更新（writer_runs vs workflow_runs） | updateWriterRunStatus 单事务 CTE 双表更新 | postgres-pi-writer-deps.ts |
| 重复草稿 | saveDraftRevision advisory lock + run 级幂等（existing 检查） | 同上 |
| 并发采纳冲突 | manuscript 块 expected_version 乐观锁；block_order 冲突 503 | writer-client.ts 注释 |
| 同项目并发生成 | LLM lease（resource_locks slot 模式，channel 级 + module 级 max_concurrency）+ 前端 composer 锁定（active runs） | acquireLLMLease |
| 事件乱序 | sequence 单调 + 前端排序；advisory lock 保证同 run 写顺序 | recordWorkflowEvent |
| 崩溃恢复 | 阶段 checkpoint（Temporal heartbeat）+ findCompletedWriterRun 重放 | worker.ts |
| 配额重复计费 | 预留→finalize；checkpoint 跳过已 finalize 阶段；provider_call_id 冲突检测 | executeLLMStage |

**未发现**的机制：无分布式锁服务（用 DB advisory lock + resource_locks 替代）；无 outbox 通用事件总线（workflow_events 即事件总线，authrecovery 有自己的 outbox 表）。

## 7. 内存泄漏与并发

- 无内存 Session 缓存（Agent 随活动销毁）；Go 侧 `TemporalWriterStarter.runs` map 无清理逻辑（run 数量增长内存会缓慢增长——低风险，仅辅助缓存）【合理推断】。
- 同一项目可同时有多个 run（无项目级串行锁）；并发上限由 LLM channel/module max_concurrency（默认来自 llm_channels.max_concurrency）控制。
