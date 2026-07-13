# 03. Multi-Tenant SaaS

更新时间：`2026-07-12`

## 目标

公网 SaaS 版本必须把“每个人前端界面不同、每个人数据不同、多用户原生并发”作为底层事实，而不是页面过滤技巧。

多租户目标：

- 每个用户只能看到自己有权限的租户、项目、文件、资产、任务和 trace。
- 团队可以协作一个项目。
- 后台任务不会串租户。
- LLM Key、小说原文、上传文件、trace 和稿件都按租户隔离。
- 支持未来套餐、计费、额度、用量和风控。

## 用户可见模型

- 产品界面统一称“工作区”；`tenant` / `tenant_id` 仅作为数据库和 API 的内部兼容命名。
- 每个账号自助注册时，原子创建且只创建一个 `personal` 工作区、一个首项目和对应 owner 关系，并直接签发首次会话。
- 一个账号不是只能属于一个工作区：它始终保留自己的个人工作区，以后还可以通过邀请加入多个团队工作区。
- 个人账号只有一个工作区时隐藏工作区切换器；加入第二个工作区后才显示切换入口。
- 工作区仍是项目、成员、LLM 渠道与绑定、配额、用量和计费的隔离边界。平台管理员不通过加入所有用户工作区来管理网站。
- 项目邀请只授予受邀项目访问；工作区邀请才授予该工作区范围的角色。

## 核心实体

### User

代表自然人账号。

关键字段：

- `user_id`
- `email`
- `display_name`
- `avatar_url`
- `status`
- `created_at`
- `last_login_at`

### Workspace（内部 Tenant）

代表个人 workspace 或组织 workspace。

关键字段：

- `tenant_id`
- `slug`
- `name`
- `tenant_type`: `personal | organization`
- `plan`
- `status`
- `created_at`

### Membership

用户和租户关系。

关键字段：

- `tenant_id`
- `user_id`
- `role`: `owner | admin | editor | writer | viewer | billing`
- `status`: `active | invited | suspended`
- `access_scope`: `tenant | project_bridge`
- `joined_at`

### Project

小说项目。

关键字段：

- `tenant_id`
- `project_id`
- `title`
- `description`
- `genre`
- `language`
- `status`
- `default_worldline_id`
- `created_by`
- `updated_at`

### ProjectMember

项目级权限覆盖。

关键字段：

- `tenant_id`
- `project_id`
- `user_id`
- `role`: `project_owner | editor | writer | analyst | viewer`

`access_scope=tenant` 的工作区成员可以按工作区角色继承项目权限；`access_scope=project_bridge` 只用于承接项目邀请，必须存在目标项目的 active project member 行，不能继承同工作区其他项目。

`0016_workspace_membership_scope_backfill` 会把升级前由项目邀请创建、且没有工作区邀请证据的旧 viewer 成员保守收敛为 `project_bridge`。回填只接受成员创建/加入时间与项目邀请接受时间一致的明确证据；原本已存在的工作区成员保持 `tenant` scope，迁移决策写入私有审计表以支持核验与定向回滚。

## 权限模型

### 工作区角色

| 角色 | 权限 |
|---|---|
| owner | 管理工作区、成员、计费、LLM 配置、所有项目 |
| admin | 管理成员和项目，不管理账单所有权 |
| editor | 创建/编辑项目、资产、图谱、worldline、稿件 |
| writer | 使用写作台、worldline、角色控制，提交草稿 |
| viewer | 只读项目数据 |
| billing | 查看用量和账单 |

### 项目角色

| 角色 | 权限 |
|---|---|
| project_owner | 项目全部权限，删除/归档项目 |
| editor | 编辑 canon 数据、资产、worldline、章节 |
| writer | 写作、续写、创建草稿、运行 reviewer |
| analyst | 上传分析、构图、维护资产和档案 |
| viewer | 只读 |

### 操作权限示例

| 操作 | 最低权限 |
|---|---|
| 查看项目 | viewer |
| 上传小说 | analyst |
| 重新运行 seed | analyst |
| 构建图谱 | analyst |
| 编辑资产 | editor |
| 采用档案记忆 | editor |
| 开始 worldline prepare | writer |
| 采用 worldline 事件为写作引用 | editor |
| 角色控制互动 | writer |
| 生成章节草稿 | writer |
| 采用正文为 manuscript | editor |
| 配置租户 LLM | admin |
| 删除项目 | project_owner |

## Tenant Context

Go API 每个请求必须解析出：

```text
request_id
auth_subject_id
user_id
tenant_id
tenant_role
project_id?
project_role?
```

tenant context 来源：

- URL path：`/[tenantSlug]/...`
- Auth claims：当前用户 id。
- DB lookup：slug -> tenant，membership。

不能从请求 body 信任 `tenant_id`。

## 数据隔离

### 表设计规则

所有租户业务表必须包含：

- `tenant_id`
- `created_at`
- `updated_at`

项目级表还必须包含：

- `project_id`

例外：

- `users`
- `tenants`
- `memberships`
- `billing_events`
- `system_model_catalog`
- `audit_logs` 可跨租户分区，但仍要记录 tenant。

### RLS 规则

Postgres 启用 RLS：

```sql
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_projects
ON projects
USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

应用连接每次事务开始设置：

```sql
SET LOCAL app.current_tenant_id = '<tenant-id>';
SET LOCAL app.current_user_id = '<user-id>';
```

### 服务角色

Worker / migration / admin job 使用 service role 时：

- 必须显式设置目标 tenant。
- 必须写 audit log。
- 不允许无 tenant 全表扫描，除非是平台管理员维护任务。

## 并发模型

### 原生并发目标

系统必须允许：

- 多租户同时上传文件。
- 多项目同时 seed。
- 多用户同时看一个任务进度。
- 同一项目中，一个用户写作，另一个用户查看资产或图谱。
- 多个 writer run 排队或并行，按项目锁策略控制。

### 项目锁

不是所有任务都能无条件并行。

| 任务 | 并发策略 |
|---|---|
| seed pipeline | 同一项目同一时间只允许一个 active seed |
| graph build | 可以和浏览并发；与 seed 写 canon 可能互斥或等待 seed 完成 |
| asset ingestion | 可并发 |
| style extraction | 可并发，但同一文件同一类型去重 |
| worldline prepare | 可并发多个 session |
| worldline auto-evolution | 同一 session 只允许一个 active evolution |
| character console | 同一 session 可多人读；写动作需要事件序列化 |
| writer run | 同一 scene/chapter 默认串行；不同 chapter 可配置并发 |
| manuscript adoption | 同一 block/revision 串行 |

### Lock 表

建议新表：

```text
resource_locks
  tenant_id
  lock_id
  resource_type
  resource_id
  owner_run_id
  lock_mode
  expires_at
  created_at
```

Temporal workflow 获取锁，完成或失败后释放。过期锁由维护任务清理。

## 个性化界面

“每个人前端界面不同”应通过真实上下文实现：

- 当前工作区不同：项目列表、LLM 配置、配额不同。
- 当前角色不同：按钮、危险操作、配置入口不同。
- 当前项目不同：模块状态、最近任务、图谱、资产、worldline 不同。
- 用户偏好不同：侧栏折叠、工作台布局、默认视图、最近打开章节不同。

### User Preferences

建议表：

```text
user_preferences
  user_id
  tenant_id
  key
  value_json
  updated_at
```

典型 key：

- `app.sidebar`
- `project.last_opened`
- `asset_library.view_mode`
- `story_graph.layout`
- `writer.workspace_layout`
- `theme`

## 配额与用量

### Quota

租户级配额：

- 每月 LLM tokens。
- 每月工作流运行次数。
- 存储空间。
- 并发任务数。
- 单文件大小。
- 最大项目数。
- 最大成员数。

### Usage Event

所有消耗型事件写入：

```text
usage_events
  tenant_id
  user_id
  project_id
  run_id
  usage_type
  quantity
  unit
  provider
  model
  cost_estimate
  metadata_json
  created_at
```

LLM 调用必须记录：

- module key。
- channel。
- model。
- prompt tokens。
- completion tokens。
- estimated cost。
- latency。
- status。

## 审计

### Audit Log

敏感操作必须写：

```text
audit_logs
  tenant_id
  actor_user_id
  actor_type
  action
  resource_type
  resource_id
  ip_hash
  user_agent
  before_json
  after_json
  created_at
```

必须审计：

- 登录失败/成功。
- 邀请成员。
- 修改权限。
- 删除项目。
- 导出数据。
- 查看大段原文 trace。
- 修改 LLM Key。
- 采用 worldline candidate 到 canon。
- 采用 agent 写作结果到 manuscript。

## 数据删除

租户删除要支持：

- soft delete 进入保留期。
- 删除 object storage 文件。
- 删除 Postgres 数据。
- 删除 vector embeddings。
- 删除 Redis 缓存。
- 删除 Temporal open workflows 或标记 cancelled。
- 生成删除审计报告。

项目删除要级联：

- 文件记录。
- seed artifacts。
- entities / relationships / graph。
- assets / archive memory。
- worldline sessions / events / agent memory。
- writer chapters / scenes / manuscript / traces。
- embeddings / global index。

## 多租户测试

必须有测试：

- User A 不能读取 User B personal tenant。
- 同一 tenant viewer 不能删除项目。
- Worker 不带 tenant_id 会失败。
- RLS 对 raw SQL 也生效。
- Graph API 不返回其他 tenant 节点。
- SSE stream 不泄露其他 tenant task。
- LLM activity 只显示当前 tenant。
