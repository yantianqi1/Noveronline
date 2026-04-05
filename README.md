# MiroFish-Novel

面向小说创作的多智能体分析与写作平台。上传小说全文，自动构建世界观图谱、角色档案与关系网络，在世界线中推演剧情走向，并通过多 Agent 协作流水线辅助创作。

## 功能概览

### 种子分析 — 从小说到结构化知识

上传小说文本（PDF / MD / TXT，最大 100 MB），平台通过四阶段 LLM 驱动管线完成深度解析：

| 阶段 | 说明 |
|------|------|
| **文本准备** | 智能分段，按 token 预算切分阅读单元 |
| **深度阅读** | LLM 逐段精读，维持跨段记忆，提取角色、关系、线索、世界观 |
| **全局整合** | 聚合所有阅读笔记，生成 seed_analysis + 故事本体 (ontology) |
| **角色构建** | 为重要角色并发生成结构化 Agent 档案（性格、语言、动机、知识边界） |

每个步骤的 LLM 调用（完整 prompt + response）均被记录，前端可逐步展开查看。

### 故事图谱

从种子分析数据构建力导向关系图谱（D3.js）。节点按重要性分层（protagonist / major / supporting / minor），边权重反映关系深度。工具栏式布局，图谱画布最大化；支持实体类型过滤、点击查看角色档案详情。

### 档案库

自动为角色、组织、关系生成结构化档案。按重要性层级使用不同模板深度：
- **protagonist / major**: 8 个维度（身份、动机、张力、关系、行为、状态、风险、隐私）
- **supporting**: 5 个维度
- **minor**: 3 个维度

档案支持搜索、筛选、重建索引，是世界线推演和写作流水线的核心数据来源。

### 世界线推演

基于单世界模型的剧情推演引擎：
- 创建世界线会话，注入变量改变剧情走向
- 角色 Agent 可独立提出动作、参与对话
- 自动推演（auto-evolution）通过 SSE 实时流式输出
- 高价值推演结果进入 candidate 记忆层，需作者审核后升级为 canon

### 写作工作台

多 Agent 协作的创作辅助系统：
- **Agent 工具循环**: 写作 Agent 拥有 write_prose / compile_manuscript / set_scene_status 等工具，自主规划写作步骤
- **世界数据写入工具**: Agent 可通过 manage_entity / manage_thread / manage_world_rule / manage_relationship 增量维护世界设定
- **世界数据更新**: 散文提交后，可一键触发 Agent 分析并更新实体、伏笔、规则等世界数据
- **实体关联查询**: query_entity 返回角色关联伏笔线索 + 适用世界规则，一次调用获取完整上下文
- **大纲版本管理**: 大纲保存时自动快照，支持版本历史浏览、预览对比、标签标注、一键恢复
- **多 Agent 流水线**: Context → Memory → Style → Writer → Reviewer 五阶段生成
- **章节 / 场景管理**: 创建章节、拆分场景、设置 POV 角色、管理预设
- **手稿阅读**: TOC 导航 + 散文视图，查看编译后的完整章节内容
- **记忆系统**: 短期记忆 (episodic) + 长期记忆 (canon / candidate / experiment) 分层管理
- **任务类型**: write_scene（场景写作）、continue（续写）、outline（章节大纲生成）

### LLM 设施面板

统一管理所有 LLM 渠道、模型与模块绑定。支持多渠道配置、模块级别的模型指定、并发控制与活动追踪。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 至少一个 OpenAI 兼容的 LLM API

### 后端

```bash
cd backend
uv sync                              # 安装依赖
FLASK_PORT=3888 uv run python run.py  # 启动服务
```

如果 `uv` 不可用：

```bash
cd backend
pip install -r requirements.txt      # 或从 pyproject.toml 安装
FLASK_PORT=3888 python3 run.py
```

### 前端

```bash
cd frontend
npm install
npm run dev -- --port 3999   # 开发服务器（自动代理 /api 到后端 :3888）
```

### 配置

复制 `.env.example` 为 `.env` 并修改：

```bash
# LLM 配置通过前端"LLM 设施面板"管理，无需在此设置 API key
LLM_REQUEST_TIMEOUT_SECONDS=120    # LLM 请求超时（秒）

# Flask
FLASK_HOST=0.0.0.0
FLASK_PORT=3888

# Zep（可选，仅在线图谱构建需要）
ZEP_API_KEY=your_zep_api_key_here
```

启动后访问 `http://localhost:3999`，在 LLM 设施面板中配置至少一个 LLM 渠道即可开始使用。

## 测试

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/                            # 全部测试
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py    # 单文件
PYTHONPATH=$(pwd) pytest tests/test_xxx.py::test_func      # 单测试
```

## 项目结构

```
backend/
  app/
    api/              # Flask REST 端点
    models/           # 数据模型（Project, Task, Worldline）
    services/         # 核心业务逻辑
      agents/         #   Agent 子系统（draft / memory / registry / worldline）
      writer_agent/   #   写作工作台服务
    utils/            # LLM client、文件解析、日志等
  tests/              # 后端测试
frontend/
  src/
    views/            # 页面组件
    api/              # 后端 API 客户端
    composables/      # Vue 组合式函数
    components/       # 复用 UI 组件
docs/
  agent-data-schema-reference.md   # Agent 数据结构与提示词参考
  superpowers/plans/  # 设计方案文档
  superpowers/specs/  # 功能规格文档
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / Flask / SQLite3 |
| 前端 | Vue 3 / Vite / D3.js v7 |
| LLM | OpenAI 兼容 API（通过设施面板统一管理） |
| 持久化 | 文件系统 + SQLite3（项目数据、档案库、LLM 设施、写作工作台） |

## 核心概念

| 概念 | 说明 |
|------|------|
| **种子分析 (Seed)** | 上传小说后的四阶段 LLM 深度解析流程 |
| **故事本体 (Ontology)** | 从小说中提取的实体类型、关系类型与叙事轴定义 |
| **档案 (Archive)** | 角色/组织/关系的结构化描述，按重要性分层 |
| **世界线 (Worldline)** | 基于单世界模型的剧情推演空间 |
| **Agent 档案** | 角色转化为可交互 Agent 所需的性格、语言、动机等数据 |
| **记忆层级** | canon（已确认）/ candidate（待审核）/ experiment（实验性） |
| **实体关联 (Entity Associations)** | 伏笔线索与世界规则自动关联到实体，查询时一并返回 |
| **大纲版本 (Outline Versions)** | 大纲保存时自动快照，支持历史浏览、预览、恢复 |
| **Chapter Context Pack** | 写作时的统一上下文（must_know / should_know / warnings） |

## 开发参考

- [Agent 数据结构与提示词参考](./docs/agent-data-schema-reference.md) — 所有 Agent 的数据 schema、LLM 提示词、参数配置
- [种子管线重设计](./docs/superpowers/specs/2026-04-03-seed-pipeline-redesign.md)
- [写作 Agent 设计](./docs/superpowers/specs/2026-04-02-novel-writer-agent-design.md)
- [手稿阅读模式设计](./docs/superpowers/specs/2026-04-04-manuscript-reading-mode-design.md)
- [大纲版本管理设计](./docs/superpowers/specs/2026-04-05-outline-versioning-design.md)

## License

Private repository.
