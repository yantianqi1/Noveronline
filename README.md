# MiroFish-Novel

面向小说创作、剧情预测、关系演化与平行世界推演的多智能体分析平台。

## 当前目标

这个仓库从 `MiroFish` 的多智能体预测底座迁移而来，但产品目标已经改为：

- 读取完整小说文本、设定、大纲与角色卡
- 提取所有有名角色、组织、势力与关系网络
- 将角色、组织、关系节点转为可演化 Agent
- 注入变量，推演平行世界分支
- 生成剧情走向、关系变化、人机关系演化与创作灵感报告
- 与角色、组织、分析 Agent 进行对话或控制行动

## 当前状态

本仓库已完成第一阶段初始化，并进入“可离线自测”的第二阶段：

- 新仓库已创建
- 旧项目中可复用的底层模块已迁移
- 小说专用的 ontology / 档案 / 平行世界配置服务已建立骨架
- 文档与 Codex 接手说明已落地
- 已补上世界线演化引擎、角色控制台与前端工作台
- 已补上离线小说种子分析：角色 / 组织 / 关系提取
- 已补上离线剧情灵感与角色对话能力
- 已加入自动生成 2000+ 汉字测试小说的端到端测试

当前仍处于“持续建设期”，但主流程已具备可验证的最小闭环。

## 已迁移的核心能力

- 文本解析与文件上传底座
- 项目文件持久化模型
- 本地图谱构建服务（`story_graph.json` + `story_graph.sqlite3`）
- 本地图谱实体读取与检索工具
- LLM 调用封装
- 小说专用 ontology 生成器
- 小说角色 / 势力档案生成器
- 平行世界配置生成器
- 世界线演化引擎
- 世界线角色对话服务
- 剧情灵感生成服务
- 离线小说种子分析器

## 当前可用主链

1. 上传完整小说文本
2. 自动生成 ontology 与离线 seed analysis
3. 提取角色、组织、关系并生成档案
4. 生成平行世界配置
5. 创建世界线会话并注入变量
6. 推进分支、与角色对话、提交角色动作
7. 输入创作灵感，获取后续剧情推进建议

## 目录结构

```text
backend/
  app/
    api/
    models/
    services/
    utils/
docs/
  plans/
frontend/
```

## 启动

当前仓库已经具备前后端工作台与后端 API，可继续离线开发。

```bash
cd backend
uv sync
uv run python run.py
```

默认端口：

- Backend: `http://localhost:5101`

提示：

- 图谱构建不再依赖 `ZEP_API_KEY`；小说解析、档案生成、世界线、角色对话与剧情灵感都可直接基于本地图谱运行。
- 所有 LLM 模块统一通过“全局设施面板”配置渠道、模型与模块绑定，不再读取旧的单组 LLM 环境变量。
- 如果需要离线运行，请显式传入 `use_llm=false`；未绑定模块时会直接报错，不做环境变量兜底。

## 测试

后端当前关键测试：

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py tests/test_offline_novel_pipeline.py
```

前端当前关键验证：

```bash
cd frontend
npm install
npm run build
```

## 关键文档

- [Codex 接手指南](./docs/CODEX_HANDOFF_GUIDE.md)
- [迁移设计文档](./docs/plans/2026-03-19-mirofish-novel-design.md)
- [迁移执行计划](./docs/plans/2026-03-19-mirofish-novel-migration-plan.md)
- [自动生成测试小说](./docs/examples/generated_parallel_world_novel.md)
