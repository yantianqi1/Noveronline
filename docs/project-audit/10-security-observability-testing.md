# 安全、可观测性与测试

## 1. 权限体系

- **认证**：会话 Cookie（可升级 JWT Bearer）、CSRF Token（`GET /v1/auth/session/csrf`）、`X-Tenant-Id`；development auth 默认关闭（`MIROFISH_ENABLE_DEVELOPMENT_AUTH`）。【已确认】server.go + auth 包。
- **RBAC**：`authorizeProject(tenant, project, permission)` 系列；permission 分级（WriterRun / CreativeWrite / AssetManage / TenantSessionManage 等）；owner-aware 资源路由（先解析真实 owner 再鉴权，不信任 body/header 身份）。
- **多租户隔离**：DB RLS + `app_set_tenant_context($1::uuid, $2::uuid, false)` 在每条查询/事务前执行（Go/Pi/Python 三端同构）；`FORCE RLS` 覆盖平台默认行（0014 migration）。
- **限流**：Redis HMAC keys（`platformratelimit`），writer run start 12 次/300s/项目+作者；auth 类 20/8 次每窗口。

## 2. Agent 工具权限

- **双层门控**：1) 工具名白名单（`runtime_context.permissions.tools`，beforeToolCall 检查，拒绝即 block）；2) 执行层再校验（`assertToolAllowed` / `assertAnalysisToolAllowed` / `assertWorldlineCastToolAllowed`）；3) 参数级租户/项目/run 一致性校验（工具参数若带 tenant_id/project_id/run_id 必须匹配运行上下文）。
- **无 shell / 无任意文件系统**：Analysis 的「文件」是 DB 表（analysis_workspace_files），路径白名单（00-plan/10-source/20-notes/30-candidates/90-review/，拒绝 `..`，≤512 字符）。
- **写入面**：仅 analysis workspace（run 作用域）+ cast commit（goal_start 状态机限定）+（运行时专用）draft 保存。无删除工具。
- **网络面**：仅模型供应商调用（base_url 来自 llm_channels，管理员配置）+ embedding 调用。无任意 URL 访问。
- **Prompt Injection 防护**【部分】：
  - 检索内容来自作者自己的项目（信任边界内）；system prompt 明确「never invent canon」「do not invent evidence」；
  - 工具结果有体积裁剪与脱敏（publicWriterToolResult 去除 content_text/alias/rule_text 等私有字段，公开事件 280 字符预览）；
  - 但**没有**针对「项目设定文本内嵌恶意指令」的显式防注入层（如指令分隔/加引号标注），【待确认】是否需要。
- **危险操作审批**：无「工具需要人工审批」机制（writer_approvals 表存在但无前端路径）。

## 3. 密钥管理

- LLM API Key：`llm_channels.encrypted_api_key`（AES-256-GCM，key 来自 `LLM_CREDENTIAL_ENCRYPTION_KEY` 环境变量，32 字节 hex/base64）；Pi/Python 运行时解密，只在本进程使用；活动 payload 不含 key。
- 会话/限流/恢复密钥均为环境变量注入，git 忽略真实值（`.gitignore`、gitleaks 配置存在）。
- 事件与 trace 脱敏：`sanitizePublicRuntimePayload`（高风险键黑名单：apiKey/authorization/body/content/draft/prompt/response/text 等）；admission options 同样 sanitize；前端 sanitize 函数过滤 UUID/错误码。

## 4. 日志、Trace、Token 与成本

| 通道 | 表/机制 | 内容 |
|---|---|---|
| LLM 活动 | llm_activity | 每次 provider 调用的 token/延迟/费用/错误 |
| 用量事件 | usage_events | 汇总用量（llm_tokens） |
| Agent trace | agent_traces + agent_trace_events | prompt_snapshot(full)、llm_call_started/completed、tool_call/tool_result(full)、assistant_message、artifact_written、error；redaction_level 三级 |
| Workflow 事件 | workflow_events | 公共事件流（脱敏） |
| 审计 | audit_logs / auth_security_audit_logs | 安全敏感操作 |
| 配额 | llm_quota_policies + llm_quota_reservations | 预留→finalize→release；token/成本/并发三类策略 |

## 5. 重试、超时、取消

- Temporal 活动重试：writer 活动 maximumAttempts=3（指数退避 5s→1min），startToClose 10 分钟，heartbeat 5s；Python 侧同族 RetryPolicy（非重试码集白名单）。
- Provider 调用：Idempotency-Key（provider_call_id + turn index）；阶段 checkpoint 恢复；quota 预留 TTL 900s。
- 超时：活动 10 分钟；前端轮询 900ms tick；SSE hold 25s 预算。
- 取消：Web cancel → DB cancelled → Temporal cancel（WAIT_CANCELLATION_COMPLETED）→ AbortSignal → agent.abort()。

## 6. 测试覆盖总览

| 层 | 数量 | 重点 |
|---|---|---|
| Go | 1073 个测试函数 | 认证、RBAC、admission 幂等、LLM 绑定、quota、事件脱敏、SSE |
| Python | 502 个测试函数（progress doc: 510 passed/31 skipped） | seed、worldline、reviewer、quota |
| Pi | 18 个测试文件（progress doc: 138 passed/4 skipped） | 工具权限、事件、recall-fusion、quota store、worker-spec、live E2E |
| Web | 124 个 test()（progress doc: 122 passed/1 skipped） | writer-run reducer、BFF 代理、页面 |
| infra | 72 个 | migrations、deployment 校验 |
| live | 隔离 `mirofish_test_*` 栈（run-live-test-stack.sh） | 真实 Postgres/Redis/Temporal/MinIO；退出 down -v |
| 契约 | shared-contracts | Go/Pi/Web 三端 JSON Schema 防漂移 |

**测试缺口**：工具级真实模型调用测试（有 live E2E 但需付费模型，仅隔离栈）；prompt 输出格式的模糊测试（解析函数有容错但未全覆盖）；跨浏览器（仅 Chromium/Playwright 记录）。

## 7. 高风险点（重点）

1. **embedding 调用不走配额预留/lease**（search_assets/search_manuscript 内 `resolveQueryEmbedding` 直连 fetch）——与「所有 provider 调用都走 executeLLMStage」的声明不一致；成本与并发控制缺口【待确认】是否在 Python 侧补齐。
2. **SSE 未启用**：后端 SSE 实现有 25s hold 预算但前端轮询——若启用需处理反代缓冲（X-Accel-Buffering 已设）。
3. **server.go 1 万行**：路由权限逻辑集中，review 难度高（有测试覆盖但人审成本大）。
4. **Pi SDK 0.80.3 旧版本**：无 Extension/Skill/RPC；升级需重测全部活动链路。
5. **analysis workspace 参数宽松**（update_todo/save_candidates additionalProperties:true）：依赖 prompt 约束 JSON 形状，模型输出异常时可能写入畸形行（有 finally 校验与 Go 侧导入校验兜底）。
