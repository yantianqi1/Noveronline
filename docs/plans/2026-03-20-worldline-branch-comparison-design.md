# Worldline Branch Comparison Design

**Goal:** 为世界线工作台补上一套“平行世界分支对比”能力，让用户能一眼看出不同 branch 在最新事件、角色状态、关系变化、待处理变量与动作上的分歧。

**Recommended Approach:** 采用“派生式分支对比摘要”。不修改 `WorldlineSession` 和 `WorldlineBranch` 的持久化结构，而是在读取 session 时由专门服务从现有 `timeline`、`actor_states`、`organization_states`、`relationship_states`、`pending_variables`、`pending_actions` 中提取对比摘要，再通过新的 comparison API 返回给前端。

## Why This Approach

- 当前世界线数据已经足够支撑“对比展示”，缺的是对人可读的聚合视图。
- 派生式摘要不需要迁移旧 session，历史世界线可直接查看。
- 对比逻辑集中在单独 service，能避免把 `worldline_session.py` 或 `worldline_engine.py` 再次堆胖。
- 后续如果要做“长期自治 agent 演化”或“多分支自动回放”，也能继续复用这层摘要服务。

## Scope

这一轮只做最贴近用户需求的主链：

- 新增 branch comparison API
- 返回每个 branch 的最新事件摘要
- 返回关键角色与组织状态快照
- 返回关系变化高亮
- 返回待处理变量与动作摘要
- 前端新增并列式对比面板

不在本轮做的内容：

- 自动评估哪条世界线“更优”
- 全量时间轴 diff 算法
- 长期自治 agent 批量并发模拟
- 复杂图谱可视化动画

## Data Design

新增 comparison 响应，不改 session 持久化模型。每个分支摘要包含：

- `branch_id`
- `title`
- `core_change`
- `current_step`
- `status`
- `latest_event`
- `key_agents`
- `key_actor_states`
- `key_organization_states`
- `relation_highlights`
- `pending`

其中：

- `latest_event` 取 branch 最后一条 timeline event
- `key_actor_states` 优先按 `key_agents` 命中角色，不足时补前几个活跃角色
- `key_organization_states` 优先补与最新事件相关或在 branch 中存在的组织
- `relation_highlights` 优先取最新事件的 `relation_changes`，没有时回退到最近的关系状态
- `pending` 聚合待处理变量名、动作 actor 与数量

同时返回一个 session 级别的 `comparison_axes`：

- `focus_question`
- `branch_count`
- `selected_branch_ids`
- `shared_variables`

## API Design

新增：

- `GET /api/worldline/session/<session_id>/comparison`

支持参数：

- `branch_ids`: 逗号分隔，可选
- `project_id`: 可选
- `graph_id`: 可选

返回：

- `session_id`
- `comparison_axes`
- `branches`

## Frontend Design

在 `WorldlineWorkbenchView` 中新增一个“分支对比面板”：

- 位置放在“分支总览”下方，与时间轴并列，形成“左侧控制 + 右侧对比”的结构
- 继续保留现有 branch 点击行为，当前选中的 branch 仍驱动时间轴
- 对比面板默认展示当前 session 全部分支
- 每张分支卡片显示：核心偏移、最新事件、关键角色状态、关系变化、待处理事项

这样用户既能看“单条时间轴”，也能同时看“多分支差异”。

## Testing

后端测试覆盖：

- comparison API 返回多分支对比摘要
- 可按 `branch_ids` 过滤分支
- latest event、关键角色状态、关系变化、pending 统计都正确

前端验证：

- `npm run build`
- 检查世界线工作台在 comparison 数据为空时也能正常渲染
