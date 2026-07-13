# Frontend UX Optimization Plan

更新时间：`2026-07-13`

## 目标

在不改变现有米纸、墨色、暗红、旧金、宋体和小说书面气质的前提下，重构 SaaS 作者工作区的信息层级、筛选、导航、详情披露和响应式布局。

本计划只借鉴 Google、Microsoft、Apple 和 Amazon / Cloudscape 的结构化 UI 思路，不复制其视觉风格。最终产品定位为“现代书卷式创作工作台”。

## 不可变视觉边界

- 保留暖纸色 `#f3eee4` / `#e9e3d8`。
- 保留深墨色 `#171a1b`。
- 保留印章红 `#8f211b` 作为唯一主动作、选中态和焦点。
- 保留旧金 `#a9854f` / `#b18a4e` 作为少量结构强调。
- 保留宋体标题、章节与正文阅读感，控件和表格使用清晰无衬线字体。
- 保留 Graph 墨色画布、Writer 手稿纸面、Worldline 时间线和 Character 剧本感。
- 不引入微软蓝换肤、Material 大圆角、Apple 大留白或 AWS 运维控制台外观。

## 信息分层

| 层级 | 内容 |
|---|---|
| 始终可见 | 当前对象、当前阶段、核心内容、阻塞原因、唯一主操作 |
| 折叠区 | 高级筛选、历史、版本、批量操作、次要统计 |
| Inspector / Drawer | 关系、证据、记忆、审校、版本差异 |
| 授权诊断 | 脱敏 Trace、调用摘要、支持编号 |
| 不进入作者 UI | README、开发文档、UUID、原始 JSON、系统 Prompt、Provider Body、数据库/队列/Worker 信息、内部错误码 |

技术内容不能只靠 CSS 隐藏。作者 API / Server Component projection 必须使用字段白名单，不下发不需要的数据；公开错误统一为“发生了什么、有什么影响、如何恢复”。

## 全局结构

```text
[创作流程导航] [项目上下文栏：项目 / 当前阶段 / 活动任务 / 搜索 / 用户]
                [紧凑书面页头                         主动作]
                [单行工具栏：搜索 / 筛选 / 排序 / 视图       ]
                [核心内容区域                    ][可折叠 Inspector]
```

- 桌面导航约 `248px`，Inspector 约 `360px` 且可折叠。
- 小于 `860px` 时导航变抽屉，Inspector 变底部 Sheet。
- 侧栏只承担项目与创作流程；账户、安全、会话和租户管理进入用户/设置菜单。
- 项目上下文栏只显示一个活动任务摘要；完整状态进入 Popover。

## 筛选模型

默认只显示一行：

```text
[搜索________________] [类型：角色 ×] [正典 ×] [筛选 3] [排序] [视图]
```

- 精确全文搜索保留在主栏。
- 只有一个最高频属性可以内联；其余条件进入统一 Filter Popover / Sheet。
- 条件按类型、状态、来源、关系、标签、时间分组。
- 已应用条件变成可移除 chips，并同步 URL。
- 零结果状态提供“清除筛选”恢复动作。
- 搜索算法、embedding、boost、ranking score 和内部模式不出现在作者界面。

## 页面蓝图

| 页面 | 默认主对象 | 渐进披露 |
|---|---|---|
| Overview | 动态“下一步”和当前产物 | 历史任务、完整就绪度、事件记录 |
| Assets | 暖纸结果列表与搜索 | Facets、批量操作、记忆与技术来源 |
| Graph | 墨色图谱画布 | Explore / Build / Curate / Compose 互斥模式、Inspector |
| Worldline | 当前世界与纸面时间线 | 角色准备、变量、历史、候选处理 |
| Character | 剧本式互动流和输入区 | 会话、角色状态、记忆、转稿动作 |
| Writer | Agent thread、作者指令、工具活动与候选正文 | 稿件/章节/审校/工作室 artifact tabs、回放、Trace、导出诊断 |
| LLM / Settings | 作者只看模块绑定状态 | 渠道、模型、配额、用量和调用记录仅管理角色 |

## 公共组件

- `WorkspaceHeader`
- `CompactFilterBar` / `FilterDisclosure`
- `InspectorPanel`
- `WorkflowProgress`
- `PublicErrorNotice`
- `SubmitButton`
- `ConfirmDialog`
- `OverflowMenu`
- `TechnicalDetailsDrawer`

## 实施波次

1. 冻结本文和 `04-design-system-and-ui.md`，建立内容边界回归测试。 **done**
2. 建立公共组件、用户错误映射、纸墨语义 token 和全局 Shell 分层。 **done**
3. 用 Assets / Overview 验证单行筛选、下一步任务和 Inspector 模式。 **done**
4. 将 Graph / Worldline / Character 的并列长表单改为互斥模式与渐进披露。 **done**
5. 让 Writer 默认聚焦 Agent 交互，将正文、结构、审校和工作室收进 artifact tabs，并将 Trace / Run ID / 事件回放移出作者主视图。 **done**
6. 拆分 LLM 作者绑定与管理员设施，统一设置层级。 **done**
7. 完成 focused/full/typecheck/build、桌面/移动截图和 DOM 隐私验收。 **in progress（Agent-first 源码契约与 focused typecheck 已通过；旧蓝色 browser 截图已撤销，待 fresh browser evidence）**

### 完成证据（2026-07-12 收口）

- 纸墨 token、`248px` 导航、`project-context-bar`；共享组件已接线。
- Assets：`CompactFilterBar` + `InspectorPanel`；Overview：`WorkflowProgress` + `SubmitButton`。
- Graph：Explore / Build / Curate / Compose 互斥。
- Worldline：`WorkspaceModeSwitcher`（start / simulate / records）。
- Character：`WorkspaceModeSwitcher`（setup / play / review）+ Inspector。
- Writer：`writer-agent-layout` 首屏双栏，主区为可恢复作者消息、工具活动、`writer.token` 候选正文、显式取消/采用与常驻 composer；右侧 `WriterArtifactTabs` 互斥承载稿件、章节、审校和工作室；诊断在 `TechnicalDetailsDrawer`（`dialog` + 焦点回触发器）。旧 `writer-studio-grid` / 折叠 composer / 深色 agent rail 已删除。
- LLM：`canManageAdmin`（tenant owner/admin）门控管理面；作者仅绑定。
- 契约：Writer-focused `frontend-ux-completion-contract` + `content-boundary` + `web-shell` + workspace/recovery tests 当前通过；`tsc --noEmit` 通过。

非阻塞后续增强：

- 为 Agent-first Writer 重新执行 production-style browser live，生成 375/768/1024/1440 截图；不得引用已撤销的蓝色长页截图。
- 后端作者 API 字段白名单可单独作为 API 层 hardening。

## 完成标准

- 每屏最多一个 primary action。
- 默认筛选栏一行，筛选状态在刷新/返回后保留。
- 所有既有用户能力最多两层可到达，没有因折叠而删除。
- 作者可见文本和 SSR HTML 不含 README、开发文档路径、UUID、原始 JSON、内部错误码、系统 Prompt 或 Provider Body。
- `375px`、`768px`、`1024px`、`1440px` 无页面横向溢出或控件重叠。
- 移动端触控目标至少 `44px`；键盘可操作 Filter、Drawer、Dialog 和 Tabs。
- 打开 Drawer / Dialog 后焦点进入，关闭后返回触发器。
- 慢请求在 `100ms` 内出现反馈，提交期间不可重复触发。
- Graph 保留大图性能与列表替代入口；Writer 保留刷新恢复、显式采用、手稿与导出完整旅程。
- 视觉回归确认纸墨红金色相、宋体标题和各模块叙事特征没有被替换。
