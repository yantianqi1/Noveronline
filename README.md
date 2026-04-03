# MiroFish-Novel

面向小说创作、剧情预测、关系演化与单世界世界线推演的多智能体分析平台。

## 当前目标

这个仓库从 `MiroFish` 的多智能体预测底座迁移而来，但产品目标已经改为：

- 读取完整小说文本、设定、大纲与角色卡
- 提取所有有名角色、组织、势力与关系网络
- 将角色、组织、关系节点转为可演化 Agent
- 注入变量，持续改写并推进当前世界线
- 生成剧情走向、关系变化、人机关系演化与创作灵感报告
- 与角色、组织、分析 Agent 进行对话或控制行动

## 当前状态

主流程已具备完整闭环，持续迭代中。

### 核心能力

- **四阶段种子分析管线**：上传小说 → 智能分段 → LLM 逐段精读（维持跨段记忆） → 全局整合（角色 / 组织 / 关系） → 故事本体生成 → 角色 Agent 档案生成
- 实时进度追踪：分段进度、章节折叠、LLM 调用计数、步骤级 trace（可展开查看完整 prompt / response）
- 任务取消支持：长时间任务可随时中断
- 本地图谱构建（`story_graph.json` + `story_graph.sqlite3`）
- 小说专用 ontology 生成器
- 角色 / 势力档案生成器（`narrative_entity_archivist`）
- 世界线演化引擎（单世界模型，变量注入 + 推演）
- 角色对话服务 + 剧情灵感生成
- 多 Agent 写作管线（context → memory → style → writer → reviewer）
- 写作工作台（章节/场景/预设管理，SSE 流式输出）
- 长期记忆分层（canon / candidate / experiment）

### 当前可用主链

1. 上传完整小说文本（PDF / MD / TXT，最大 100MB）
2. 四阶段种子分析：智能分段 → 顺序深度阅读 → 全局整合 → 角色 Agent 档案
3. 自动生成 ontology，提取角色、组织、关系并生成档案
4. 创建世界线会话并注入变量
5. 推进当前世界、与角色对话、提交角色动作
6. 在 `/writer` 生成 Chapter Context Pack，拿到写作上下文与 prompt block
7. 在作者工作台审核长期记忆 candidate / canon
8. 输入创作灵感，获取后续剧情推进建议

## 种子分析管线

四阶段 LLM 驱动的顺序阅读管线（替代旧版 14 阶段并发分析）：

| 阶段 | 关键模块 | 进度范围 |
|------|---------|---------|
| 文本准备 | `smart_novel_segmenter` — 按 token 预算分段 | 0–10% |
| 深度阅读 | `sequential_reader` — 逐段精读，维持弧线/卷摘要 | 10–75% |
| 全局整合 | 聚合 `seed_analysis.json` + 故事本体 | 75–90% |
| 角色构建 | `character_agent_profile_generator` — 并发生成角色档案 | 90–100% |

每个步骤的 LLM 调用（prompt + response）会被记录到 trace bundle 文件，前端可展开查看。

## 写作上下文与记忆审核

围绕单世界创作流程组织能力：

- `Chapter Context Pack` 是作者侧的统一写作上下文，固定输出 `must_know / should_know / warnings / scene_candidates / writer_prompt_block / debug_trace`
- `/writer` 页面同时支持原著章节模式和 worldline 分支模式
- 长期记忆采用 `canon / candidate / experiment` 分层，其中默认写作链路只注入 active `canon`
- worldline 自动推演产生的高价值记忆先进入 `candidate`，需要作者审核后才能晋升为 `canon`
- 记忆 timeline 会保留版本、状态、来源与事件链，方便追溯”这条设定是怎么来的”

## 目录结构

```text
backend/
  app/
    api/          # Flask blueprints (REST endpoints)
    models/       # 数据模型与持久化
    services/     # 业务逻辑（种子管线、世界线、写作管线等）
    utils/        # LLM client、文件解析、JSON 修复等
docs/
  plans/
  superpowers/    # 设计规格与实现计划
frontend/
  src/
    views/        # 页面组件（Overview、Writer、WorldLine 等）
    api/          # 后端 API 客户端
    composables/  # Vue 组合式函数
    components/   # 复用 UI 组件
```

## 启动

### 后端

```bash
cd backend
uv sync                              # 安装依赖
FLASK_PORT=3888 uv run python run.py  # 启动（端口可选，默认 5101）
```

如果 `uv` 不可用：

```bash
cd backend
FLASK_PORT=3888 python3 run.py
```

### 前端

```bash
cd frontend
npm install
npm run dev -- --port 3999   # 开发服务器（代理 /api 到后端）
npm run build                # 生产构建
```

### 提示

- 图谱构建不依赖 `ZEP_API_KEY`，所有核心功能基于本地图谱运行
- LLM 模块通过”全局设施面板”统一配置渠道、模型与模块绑定
- 未绑定模块时直接报错，不做环境变量兜底

## 测试

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py tests/test_offline_novel_pipeline.py   # 关键测试
PYTHONPATH=$(pwd) pytest tests/test_new_seed_pipeline.py tests/test_step_trace.py               # 种子管线测试
PYTHONPATH=$(pwd) pytest tests/                                                                  # 全部测试
```

## 关键文档

- [Codex 接手指南](./docs/CODEX_HANDOFF_GUIDE.md)
- [种子管线重新设计规格](./docs/superpowers/specs/2026-04-03-seed-pipeline-redesign.md)
- [迁移设计文档](./docs/plans/2026-03-19-mirofish-novel-design.md)
- [迁移执行计划](./docs/plans/2026-03-19-mirofish-novel-migration-plan.md)
