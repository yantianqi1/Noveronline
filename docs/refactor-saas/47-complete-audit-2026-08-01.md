# 47 · 完整项目审核报告（2026-08-01）

> 审核对象：Noveronline-saas-mainline（MiroFish SaaS 多租户小说创作平台 monorepo）
> 审核日期：2026-08-01
> 代码规模：Python 98.9k 行（535 文件）+ Go 75.7k 行（251 文件）+ TS/TSX 32.5k 行（212 文件），约 20 万行
> 审核方式：静态安全扫描（bandit/grep）→ 依赖 CVE（OSV/npm audit）→ 测试验证 → 双子代理独立深度审查（Go API + Python backend）→ 关键发现逐条人工验证
> 前置文档：`46-prelaunch-bug-audit-round2.md`（2026-07-31 上轮审计基线）

---

## 总览

| 级别 | 数量 | 说明 |
|---|---|---|
| 🔴 Critical | 7 | 必须优先修复（认证绕过 / IDOR / CORS / SSRF / 租户隔离 / 注册枚举） |
| 🟠 Warning | 8 | 尽快处理（依赖漏洞 / 连接池 / 测试失败 / 路径穿越） |
| 🟡 Suggestion | 6 | 建议优化（重复代码 / 巨型文件 / 声明性标注） |

---

## 🔴 Critical（7 项）

### C1 · Python 后端全站 API 无认证

- **位置**：`backend/app` 全站（api_fastapi 下除 LLM 渠道写接口外所有路由）
- **问题**：项目 / 章节 / 手稿 / 资产等 API 无任何鉴权，`tenant_id` / `project_id` 直接来自请求体，任意网络可达者可读写全部数据。
- **影响**：数据全量泄露与被篡改。
- **修复建议**：接入统一认证中间件（会话 token 或 API key），所有业务路由默认要求认证。

### C2 · `/api/v2` 前缀绕过 ADMIN_SECRET 认证

- **位置**：`backend/app/middleware/auth.py:12-15` + `backend/app/api_fastapi/__init__.py:29-34`
- **问题**：`LLM_WRITE_PREFIXES = ("/api/llm/channels", "/api/llm/module-bindings")` 用 `request.url.path.startswith(...)` 匹配，而 llm 路由同时挂在 `api_v2_router = APIRouter(prefix="/api/v2")` 下。`/api/v2/llm/channels` 不匹配前缀 → 认证被绕过。✅ 已验证。
- **影响**：未认证可修改 LLM 渠道配置（存储第三方 API key 的敏感配置）。
- **修复建议**：改用路由级依赖（`Depends(require_admin)`）而非中间件前缀匹配；或统一路由挂载位置。

### C3 · 资产 IDOR（跨项目改删任意资产）

- **位置**：`backend/app/services/assets/assets_service.py:109-148`（update/delete）+ `backend/app/repositories/asset_repo.py:86,102`（`update_asset` / `delete_asset`）
- **问题**：`update_asset` / `delete_asset` 的 WHERE 仅 `asset_id`，无 scope / project_id 条件。✅ 已验证。
- **影响**：知道 asset_id 即可跨项目修改 / 删除任意资产。
- **修复建议**：repo 层强制带 `project_id`（或 scope）条件；service 层先做归属校验。

### C4 · CORS 通配 + 任意 Origin 回显 + PNA

- **位置**：`backend/app/main.py:195-215`（`_register_middleware`）
- **问题**：`allow_origin_regex=".*"` + `_private_network_cors` 任意 Origin 回显 + `allow_private_network=True` + `Access-Control-Allow-Private-Network: true` 回显。✅ 已验证。
- **影响**：恶意网页（含内网）可直接读写本地后端。
- **修复建议**：CORS 白名单收敛；禁用 PNA 头回显；Origin 校验后回显。

### C5 · LLM 渠道 base_url 无校验 → SSRF

- **位置**：`backend/app/services/llm_settings_service.py` + `backend/app/utils/llm_client.py`
- **问题**：LLM 渠道 `base_url` 无协议 / 内网地址校验，请求体可指向 `169.254.169.254`（云元数据）或攻击者服务器。
- **影响**：SSRF——元数据窃取、小说正文外泄。
- **修复建议**：base_url 白名单 / 协议限制 / 内网段禁访。

### C6 · Go 端多租户隔离依赖逐 handler 手动授权

- **位置**：`apps/api/internal/httpapi/server.go:3738` 起约 70 处 `X-Tenant-Id` 头读取；`infra/postgres/migrations/0001_core_saas.sql:13-28, 1926-1930`（RLS 策略仅按 `app.current_tenant_id` 过滤，无用户谓词）
- **问题**：租户上下文 = 客户端可伪造的 HTTP 头；服务器无中间件级"actor + tenant"绑定；RLS 层对用户身份零校验（部分读路径 `app_set_tenant_context($tenantID, NULL, ...)` 传 NULL 用户）。授权正确性 100% 依赖每个 handler 记得调 `authorizeProject*`——上一轮审计的 3 个 BLOCKER 正是此模式漏网（已修复）。
- **影响**：任一新增 / 被遗忘的 handler 漏调授权 = 未认证跨租户读取。
- **修复建议**：`ServeHTTP` 增加中间件级强制授权（解析 actor + 路径 projectId 统一执行 ProjectRead 授权入 context）；`X-Tenant-Id` 从会话派生而非信任请求头；RLS 增加 `app.current_user_id` 谓词作第二道防线。

### C7 · 注册无邮箱验证 + 邮箱枚举

- **位置**：`apps/api/internal/registration/service.go:116`（`INSERT ... status='active'`）+ `:306`（`emailConflictError` 明确返回 "an account with this email already exists"）
- **问题**：`AllowSelfSignup` 开启时任意合法邮箱直接建 active 用户，可抢注他人邮箱；注册冲突 409 与登录区分，构成定向枚举。✅ 已验证。
- **影响**：账户接管前置（抢注 + 密码重置流劫持）。
- **修复建议**：注册后邮箱验证（一次性链接，未验证不可登录 / 不可触发重置）；冲突响应统一为通用消息；或默认关闭 signup 端点。

---

## 🟠 Warning（8 项）

### W1 · 依赖已知漏洞（最高优先）

| 依赖 | 当前版本 | 漏洞 | 修复版本 |
|---|---|---|---|
| `github.com/jackc/pgx/v5` | v5.8.0 | **CVE-2026-33815 / CVE-2026-33816（CRITICAL 内存安全）** + CVE-2026-41889（LOW SQL 注入） | **≥ 5.9.2** |
| `starlette` | 1.0.0 | **10 个漏洞**：GHSA-86qp（Host header 污染）、GHSA-wqp7（SSRF/UNC 路径）、GHSA-x746（任意 HTTP 方法调度）、GHSA-jp82（URL authority 污染）等 | **≥ 1.3.1** |
| `golang.org/x/crypto` | v0.47.0 | 27 个漏洞（7 CRITICAL，集中在 ssh/agent 子包；项目仅用 bcrypt，实际影响小） | **0.52.0** |

- 验证来源：OSV API（`api.osv.dev/v1/query`），npm audit 0 漏洞 ✅。
- 注意：升级 starlette 需同步验证 fastapi 0.135.3 兼容性。

### W2 · Go 端约 70 个独立 `sql.DB` 连接池互不复用

- **位置**：`apps/api/cmd/api/main.go:54-64`（`openAppDatabase`，每池 `SetMaxOpenConns(1)`），被调用约 70 次（:1421、:1441、:1565 … :2997）
- **问题**：每 store/starter 各自新建连接池，上限 1，互不共享；单进程常驻连接 70+。
- **影响**：启动开销大、连接数线性膨胀、突发并发互相争抢。
- **修复建议**：main 中创建 1 个共享 app 连接池（如 `MaxOpenConns=20`）依赖注入复用；只读查询可走只读副本池。MinIO 客户端与 Redis 限流器为装配时单例复用，无此问题。

### W3 · `ForceSecureSessionCookies` 配置项未生效

- **位置**：`apps/api/internal/httpapi/server.go:3302-3310` 及所有 `SetCookie` 调用：`Secure: request.TLS != nil`
- **问题**：`Config.ForceSecureSessionCookies` 被存储（:1160）但从未在写 cookie 路径使用。
- **影响**：反代终结 TLS 场景（Go 看到 HTTP），会话 / CSRF cookie 不带 `Secure` 标志，明文信道泄露。
- **修复建议**：`Secure: request.TLS != nil || s.forceSecureSessionCookies`；反代场景校验 `X-Forwarded-Proto`。

### W4 · step trace 路径穿越

- **位置**：`backend/app/api_fastapi/project.py:284`（`get_step_trace`，`step_id` 未清洗直接拼路径）✅ 已验证
- **影响**：`load_step_bundle(project_id, task_id, step_id)` 中 step_id 可控时可越界读取文件。
- **修复建议**：step_id 校验格式（如 uuid / `[a-zA-Z0-9_-]+`），禁止路径分隔符。

### W5 · 上传无大小限制 / writer-runs 公共 API tenant 可控

- **位置**：`backend/app` writer-runs 公共 API；上传路径
- **问题**：`MAX_CONTENT_LENGTH` 定义了但未启用；tenant 由客户端提交。
- **影响**：存储耗尽 DoS；跨租户数据污染。
- **修复建议**：启用 body 大小限制中间件；tenant 从会话派生。

### W6 · 响应回传原始错误文本

- **位置**：`apps/api/internal/httpapi/server.go:5912`（SearchAssets）、:5939/5966、:6732（AdoptAsset）；`assets/assets.go` 多处 `AppError.Message` 拼接 `err.Error()`
- **影响**：DB 驱动错误（SQLSTATE、约束名、表/列名）泄露 schema 信息。
- **修复建议**：统一 `publicAppErrorMessage(code)` 映射，原始错误只进日志（`request_id` 关联）。

### W7 · 未提交改动测试失败（2 个）

- **位置**：`apps/agent-runtime/tests/test_seed_workflow_monitor.py`（当前未提交改动）
- **失败 1**：L178 断言 `tenant_contexts == [((("t1", None, False),))]`，但生产代码 `app_set_tenant_context(%s::uuid, NULL, false)` 只传 1 个参数（`NULL`/`false` 是 SQL 字面量）→ **断言写错**，应为 `[("t1",)]`
- **失败 2**：L292 `rows_t1 + rows_t2` 是 dict 列表，**漏了 `_rows_as_cursor_rows()` 转换**（其他测试都转了），导致 `dict(zip(columns, dict))` 把列名当值 → KeyError `'temporal_workflow_id'`
- **结论**：均为测试代码 bug，生产代码正确，修测试即可。运行结果：`2 failed, 5 passed`。

### W8 · 写工具无确认 / 回滚

- **位置**：`backend/app` 写工具（`splice_block` 直接改正式手稿）
- **影响**：间接提示注入可持久化破坏手稿内容。
- **修复建议**：写操作加确认、版本历史、可回滚。

---

## 🟡 Suggestion（6 项）

1. **SHA1 稳定哈希 5 处重复实现**：`worldline_engine.py` / `local_story_graph_support.py` / `worldline_agent_registry.py` / `archive_library_service.py`（backend）+ `legacy_import/models.py`（agent-runtime）→ 合并到公共工具模块（DRY）。
2. **巨型文件拆分**：`apps/api/internal/httpapi/server_test.go` 22.9k 行、`apps/agent-runtime/mirofish_agents/temporal/seed.py` 12.2k 行、`apps/api/internal/httpapi/server.go` 10.4k 行。
3. **SHA1 加 `usedforsecurity=False`**：4 处 bandit B324 误报消除，同时显式声明非安全用途（`archive_library_service.py:82`、`local_story_graph_support.py:51`、`worldline_agent_registry.py:34`、`worldline_engine.py:585`）。
4. **`handleCreateDevSession` 身份伪造后门**：建议加 `MIROFISH_ENV != production` 双保险。
5. **手稿块写操作保留版本历史**。
6. **JWT 校验无 `nbf`**：建议会话轮换时间戳跟踪。

---

## ✅ 良好实践（确认无问题）

- **无硬编码密钥**：grep 全仓命中的均为测试占位符（test-only-key、live-test、example.test）。
- **无危险函数**：eval / exec / os.system / pickle / shell=True 命中全部位于 `backend/.venv/` 第三方库，项目自有代码零命中。
- **`.env` 防护到位**：仅 `.env.example` 入库，真 `.env` 均被 `.gitignore` 排除（含 backend/.env、apps/api/.env）。
- **Go 认证核心质量高**：HMAC 常量时间比较、会话 token 哈希存储、bcrypt dummy hash 防枚举、CSRF 双提交、JWT 手工校验完整。
- **postgres_search.py:72 SQL 拼接为误报**：实际是参数化占位符（`:key` + params 传值）。
- **上传文件用 uuid 重命名落盘**，无路径穿越。
- **上一轮审计 3 个 BLOCKER 已修复**（seed-runs 列表、asset-ingestion 详情、style-extraction 详情，server.go:6203/6273/4288 已加 lookup 后授权；archive-memory 读侧 5929/5956 已加 `authorizeArchiveAssetProjectRead`）。
- **npm audit：0 漏洞**。

---

## 建议修复顺序

1. C2（v2 认证绕过）
2. C3（资产 IDOR）
3. C4（CORS 通配）
4. W1（依赖升级：pgx → 5.9.2、starlette → 1.3.1、x/crypto → 0.52.0）
5. W7（修 2 个测试 bug）
6. C1（全站认证）
7. C6 / C7（Go 端租户隔离中间件 + 注册流程）

---

## 附录：审核工具与命令

- 静态安全：`bandit 1.8.6`（backend/app，25 发现：4 HIGH 均为 SHA1 误报、6 MEDIUM 为 SQL 拼接误报 / 白名单兜底）+ grep 全仓模式扫描
- 依赖 CVE：OSV API（`api.osv.dev/v1/query`）批量查询 + `npm audit --registry=https://registry.npmjs.org`（0 漏洞）
- 测试：`pytest tests/test_seed_workflow_monitor.py`（2 failed, 5 passed）
- 深度审查：2 个独立子代理并行（apps/api Go 后端 + backend Python 后端），关键发现逐条人工验证
- 代码量：pygount summary（排除 .git/node_modules/.venv 等）
