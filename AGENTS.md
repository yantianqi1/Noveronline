# AGENTS.md

## 目的
这份文档是 `MiroFish-Novel` 的交接手册，目标是让后续 AI 在**暂时不看源码**时，也能先准确理解项目定位、当前进度、验证状态、在建功能和后续优先级。
更新时间：`2026-03-25`

## 一句话定位
`MiroFish-Novel` 是从 `MiroFish` 迁移出来的小说多智能体平台，核心目标不是舆情分析，而是：
- 读取小说文本、设定、大纲、角色卡
- 提取角色 / 组织 / 关系 / 世界规则
- 建立单世界 worldline 并持续推进
- 支持角色对话、变量注入、剧情灵感生成
- 为作者生成可直接消费的写作上下文与正文草稿

当前主链可概括为：
`上传小说 -> seed analysis / ontology / 档案 -> worldline -> 推演 / 对话 / 记忆审核 -> writer -> 正文生成`

## 当前阶段判断
- 项目已经越过“空壳/骨架”阶段，进入**可离线验证的功能建设期**
- 核心主链已覆盖：上传、seed analysis、档案、worldline、writer、记忆审核、剧情灵感
- 前端已有多个实际工作台，不是占位页
- 后端测试体系已覆盖关键链路
- 当前工作区存在未提交开发，重点在“多 Agent 正文生成”和“worldline 工作台重构”

可以把当前状态定义为：
**Phase 2.5：离线可跑，写作链路初步闭环，正在向真实作者协作工具推进。**

## 已完成能力

### 1. 小说上传与异步种子分析
已具备：上传 TXT / MD / PDF、创建项目与文件持久化、异步章节切分与种子分析、任务状态查询与缺失任务恢复。
代表接口：`POST /api/project/seed/extract`、`GET /api/project/task/<task_id>`、`GET /api/project/list`、`DELETE /api/project/<project_id>`

当前约束：
- `seed/extract` 仅支持 `LLM` 模式
- 未绑定模块应直接报错，不做静默兜底

### 2. Seed Analysis / Ontology / 档案
已具备：提取角色 / 组织 / 关系、生成 `seed_analysis.json`、从 graph 或 seed analysis 生成档案候选、生成 narrative archives 并同步档案库。
代表接口：`POST /api/novel/seed-analysis`、`POST /api/novel/archives/candidates`、`POST /api/novel/archives/generate`、`GET /api/archive/library`

### 3. 单世界 Worldline
已具备：session 创建、当前世界推进、自动演化、变量注入、timeline 查询、agent roster / action / dialogue / memory 查询。
代表接口：`POST /api/worldline/session/create`、`GET /api/worldline/session/<session_id>/timeline`、`POST /api/worldline/session/<session_id>/step`、`POST /api/worldline/session/<session_id>/auto-evolve`、`POST /api/worldline/session/<session_id>/inject-variable`、`GET /api/worldline/session/<session_id>/agents`

重要事实：
- 当前仓库已转向**单世界** worldline
- 旧的 `/branches`、`/comparison` 已主动废弃并返回 `410`
- 当前前后端都围绕 `current_world` 组织

### 4. Writer 工作流与 Chapter Context Pack
已具备：`/writer` 页面、`project_chapter` / `worldline_branch` 两种范围、POV 选择、`Chapter Context Pack`、candidate 记忆时间线查看、candidate -> canon 审核。
代表接口：`GET /api/novel/chapter-context/options`、`POST /api/novel/chapter-context`、`GET /api/archive/library/<archive_id>/memory/timeline`、`POST /api/archive/library/<archive_id>/memory/<memory_id>/adopt`

这说明项目已经从“分析工具”进入“作者可消费工具”阶段。

### 5. 角色对话与剧情灵感
已具备：世界线角色对话、角色历史 / 动作 / 对话 / 记忆查询、创作者灵感生成后续剧情建议。
代表接口：`POST /api/worldline/session/<session_id>/agent-dialogue`、`GET /api/worldline/session/<session_id>/agent-history`、`GET /api/worldline/session/<session_id>/agent-memory`、`POST /api/novel/plot/inspiration`

### 6. 全局 LLM 设施面板
已具备：channel 配置、模型同步、模块绑定 / 解绑。
关键原则：所有 LLM 调用统一走全局设施面板；不再使用旧项目单组环境变量；未绑定模块时应显式失败。
代表接口：`GET /api/llm/settings`、`POST /api/llm/channels`、`POST /api/llm/channels/<channel_key>/sync-models`、`PUT /api/llm/module-bindings/<module_key>`

## 当前前端页面状态
前端已有完整工作台路由：`/`、`/guide`、`/archive-library`、`/story-graph`、`/worldline`、`/writer`、`/character-console`、`/llm-facility`。
当前判断：首页、writer、worldline、character-console 都已有明确产品语义，项目已从“先做后端”进入“前后端一起塑形”阶段。

## 目录与责任划分
Backend：Python 3.11、Flask、Pydantic、OpenAI-compatible client；核心目录是 `backend/app/api`、`backend/app/services`、`backend/app/models`、`backend/app/utils`、`backend/tests`；优先理解 `story_ontology_generator.py`、`novel_seed_analyzer.py`、`narrative_entity_archivist.py`、`chapter_context_pack_builder.py`、`archive_memory_review_service.py`、`worldline_engine.py`、`worldline_runtime_service.py`、`character_agent_service.py`、`plot_inspiration_engine.py`、`llm_router.py`。
Frontend：Vue 3、Vue Router、Vite、D3；核心目录是 `frontend/src/views`、`frontend/src/components`、`frontend/src/api`、`frontend/src/composables`。

## 数据存储与运行时事实
- 项目文件和中间产物位于 `backend/uploads/projects/`
- 本地图谱产物是 `story_graph.json` 与 `story_graph.sqlite3`
- LLM 设施配置使用本地 SQLite
- 档案库使用本地 SQLite
- worldline 运行时状态使用文件系统持久化
- 前端默认端口：`3891`
- 后端默认端口：`5101`
- 每次超过 50 行代码改动后，需要完整重启前后端

## 本次已验证的状态
前端已验证：
- 命令：`cd /Users/项目/MiroFish-Novel/frontend && npm run build`
- 结果：构建成功，产物正常，耗时约 `1.20s`

后端已验证：
- 命令：`cd /Users/项目/MiroFish-Novel/backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 /Users/项目/MiroFish-Novel/.venv/bin/python -m pytest tests/test_offline_novel_pipeline.py tests/test_worldline_engine.py tests/test_chapter_context_api.py tests/test_archive_memory_review_api.py tests/test_draft_agents.py`
- 结果：`31 passed in 0.71s`

这次明确验证通过的链路：离线小说主链、worldline engine、chapter context API、archive memory review API、draft agents 基础逻辑。

## 当前工作区里的在建功能
当前 git 工作区不是干净状态，存在未提交改动，核心方向如下。

### A. 多 Agent 正文生成正在并入主写作台
已能确认：
- 新增 `backend/app/services/draft_agents/`
- 已有 `context_agent / memory_agent / style_agent / writer_agent / reviewer_agent / orchestrator`
- `POST /api/novel/draft/generate` 已新增为 `SSE` 流式接口
- 前端新增 `frontend/src/api/sse.js`
- `/writer` 已被改造成“上下文 + Agent 进度 + 流式正文 + 审校报告”的形态

当前判断：
- 这条链路已经进入主功能区，不再只是概念验证
- 但仍属于**未提交中的在建功能**，不要把它当作完全稳定发布态

### B. Worldline 工作台正在重构
已能确认：
- 新增 `WorldlineSelectionPanel.vue`
- 新增 `WorldlineSimulationRoster.vue`
- `WorldlineWorkbenchView.vue`、`WorldlineControlPanel.vue`、布局相关文件均有未提交修改
- 方向是“选择栏 / 控制栏 / 导演台”的多栏工作台

当前判断：
- 这是产品交互层重构，不是底层引擎重写
- 目标是提升连续操作体验，而不是改变 worldline 基础语义

### C. LLM 文本保真和模块注册仍在继续调整
当前涉及：
- `backend/app/services/llm_module_registry.py`
- `backend/app/utils/llm_client.py`

判断：
- 大概率是为 writer / draft agent / worldline 这些更复杂的生成链路服务

## 当前最重要的已知问题
### 1. 当前 shell 不保证有 `uv`
本机直接运行 `uv` 会报 `command not found`，后续 AI 不要默认依赖 `uv run pytest`。

### 2. 中文路径下虚拟环境可能触发编码问题
仓库路径是：`/Users/项目/MiroFish-Novel`
如果直接运行：
- `/Users/项目/MiroFish-Novel/.venv/bin/python -m pytest ...`
可能触发 `UnicodeDecodeError`。

已验证可行的绕过方式：显式加 `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1`

### 3. Writer 正文生成仍在收口中
当前状态应理解为：
- `Chapter Context Pack` 与记忆审核已是稳定主链
- “多 Agent 直接产出正文”已开始落地
- 但正文生成还不应被视为最终稳定形态

## 与上游 `MiroFish` 的关系
上游参考项目：本地路径 `/Users/项目/MiroFish`，GitHub `https://github.com/666ghj/MiroFish`。
允许优先借鉴：文件上传与文本解析、项目持久化与任务状态管理、图谱构建、Zep 实体读取、LLM 封装、前后端工作流编排。
不要照搬：Twitter / Reddit / 舆情语义、平台指标外壳、不匹配小说领域的 ontology、老旧前端 API 契约。
迁移原则：先查当前仓库是否已有实现；有现成实现就不要回迁；真要迁移也必须先做“小说语义适配”。

## 后续 AI 的推荐阅读顺序
如果时间有限，推荐按这个顺序建立上下文：
1. 先读本文件 `AGENTS.md`
2. 再读 `README.md`
3. 再读 `docs/CODEX_HANDOFF_GUIDE.md`
4. 再看 `git status --short`
5. 最后才决定是否深入具体源码

如果只想快速理解主链，优先聚焦：`project` 上传与任务、`novel` 的 seed / archive / chapter-context / draft、`worldline` 的 session / step / auto-evolve / interaction、`archive memory review`、前端的 `/writer`、`/worldline`、`/character-console`。

## 后续开发建议
### P0：把 Writer 正文生成链路收口
原因：
- 当前最接近产品价值闭环的是作者工作台
- `Chapter Context Pack`、记忆审核、POV 选择已经齐了
- 多 Agent draft 已开始接入，只差收尾和稳定化

建议动作：明确 draft 请求契约和失败语义；补正文生成成功 / 失败 / 中断 / 重试的端到端测试；明确 revision mode 输入输出契约；把上下文条目点击与记忆时间线联动补完整。

### P1：完成 Worldline 工作台重构并稳定交互
原因：
- worldline 是小说推演主场景
- 结构重构已经开始，半途停下维护成本会更高

建议动作：完成选择栏 / 控制栏 / 导演台三栏协作；保证 session 创建、自动演化、变量注入、timeline 刷新是一套稳定链路；提升角色 roster、当前世界摘要、关键事件摘要的视觉层级。

### P1：补齐 Writer 与 Worldline 的桥
建议动作：明确 worldline_branch -> writer 的默认上下文策略；区分 canon / candidate / experiment 在写作阶段的注入规则；让“为什么这条记忆进入当前 pack”更可解释。

### P2：提高端到端回归测试代表性
建议动作：增加 `/writer` 多 Agent 生成链路测试；增加 worldline -> inspiration -> writer 的集成测试；增加前端关键页面 smoke test。

### P2：谨慎决定在线图谱能力是否继续推进
建议动作：只有在真实需要 Zep 在线能力时再补端到端；在此之前优先打磨本地图谱 + 写作消费链。

## 接手时的执行建议
如果另一个 AI 接手后要直接开始做事，默认顺序建议是：
1. 先确认当前 `git status`
2. 判断这次是否要继续未提交中的 writer / draft / worldline 重构
3. 如果是，就围绕 `/writer` 和 `draft_agents` 收口
4. 如果不是，再回到已稳定主链继续推进

不要默认大改：ontology 语义、社媒遗留抽象、多分支世界线设计。

当前真正的价值中心已经转向：
**作者工作流、单世界推演、记忆审核、正文生成。**
