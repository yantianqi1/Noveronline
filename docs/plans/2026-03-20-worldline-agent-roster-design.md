# Worldline Agent Roster Design

**Goal:** 为世界线会话补上统一的 agent 名册，让角色、组织、关系都能自动生成 agent 卡片，并能在控制台直接点选、查看、对话、下动作。

**Recommended Approach:** 采用“派生式 agent registry”。不把 agent 名册作为新的主存储结构写死在 session 模型里，而是基于每个 branch 现有的 `actor_states`、`organization_states`、`relationship_states` 动态生成 agent 卡片。这样改动面最小，兼容已有世界线数据，也更容易继续演进成长期自治 agent。

## Why This Approach

- 当前世界线 branch 已经持有三类核心状态：角色、组织、关系。
- 用户真正缺的是“统一入口”和“稳定 agent_id”，而不是再造一套独立存储。
- 动态派生可以避免旧 session 数据迁移，降低回归风险。
- 后续如果要升级为长期自治 agent，只要把派生卡片替换为持久化卡片即可。

## Scope

这一轮只补最关键的缺口：

- 为角色 agent 生成稳定 `agent_id`
- 为组织 agent 生成稳定 `agent_id`
- 为关系 agent 生成稳定 `agent_id`
- 增加世界线 agent 名册 API
- 支持通过 `agent_id` 与任意 agent 对话
- 支持通过名册点选 agent，再提交动作
- 在前端控制台展示 agent 名册

不在本轮做的内容：

- 长期记忆型自治 agent
- 跨 session 共享 agent 身份
- 关系 agent 的专属复杂策略引擎
- 多 agent 自动并发博弈调度器

## Data Design

每个 agent 卡片至少包含：

- `agent_id`
- `agent_kind`: `character | organization | relationship`
- `display_name`
- `source_ref`
- `summary`
- `role`
- `drive`
- `tension`
- `branch_id`
- `can_chat`
- `can_act`

其中：

- 角色 agent 由 `actor_states` 派生
- 组织 agent 由 `organization_states` 派生
- 关系 agent 由 `relationship_states` 派生

关系 agent 使用稳定 ID，例如：

- `relation::沈夜::玄霄宗`

显示名使用更适合人读的形式，例如：

- `沈夜 × 玄霄宗`

## API Design

新增：

- `GET /api/worldline/session/<session_id>/agents`
  返回当前 branch 或默认 branch 的 agent 名册

保留并增强：

- `POST /api/worldline/session/<session_id>/agent-dialogue`
  允许直接传 `agent_id`
- `POST /api/worldline/session/<session_id>/agent-action`
  允许直接传 `agent_id`

## Behavior Design

### Dialogue

- 角色 / 组织 agent：沿用现有本地回复逻辑
- 关系 agent：把关系状态映射成一张“关系人格卡”，再复用同一套回复服务

### Action

- 角色 / 组织 agent：沿用现有 pending action 流程
- 关系 agent：也允许提交动作，branch 推进时优先写回匹配关系项的 `last_action`、`status`、`note`

## Frontend Design

在角色控制台新增一个 agent 名册面板：

- 输入 session_id 后可刷新 agent 列表
- 按角色 / 组织 / 关系分组展示
- 点击卡片后自动填充聊天对象与动作对象
- 直接显示摘要、动机、张力、最近动作

## Testing

新增后端测试覆盖：

- agent 名册 API 返回角色、组织、关系三类 agent
- 关系 agent 可通过 `agent_id` 发起对话
- 关系 agent 可通过 `agent_id` 提交动作并在 step 后写回关系状态

前端验证：

- `npm run build`

