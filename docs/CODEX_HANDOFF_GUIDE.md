# Codex 接手指南：MiroFish-Novel

## 项目定位

这是一个从 `MiroFish` 迁移出来的新仓库，目标不是通用舆情预测，而是：

- 小说世界图谱构建
- 角色 / 势力 / 组织档案生成
- 人机关系与人物关系演化分析
- 当前世界变量注入与持续推进
- 剧情走向推演
- 与角色 / 势力 agent 的互动

## 当前阶段

当前已进入“离线可跑 + 世界线可测”阶段，已完成：

- 新仓库创建
- 可复用的工具层、模型层、图谱层迁移
- 小说专用 ontology 服务创建
- 小说档案生成服务创建
- 基础 API 建立
- 单世界世界线演化引擎与文件系统持久化
- 世界线自动演化任务与当前世界控制台
- 世界线角色对话 / 角色动作接口
- 作者工作台 `/writer`，可生成 Chapter Context Pack 并查看 debug trace
- 长期记忆 V2：candidate / canon 分层、审核接口、timeline 追溯
- 剧情灵感生成接口
- 离线 seed analysis：角色 / 组织 / 关系提取
- 前端工作台骨架
- 自动生成 2000+ 汉字测试小说并执行端到端回归测试

## 默认开发原则

- 优先保留旧项目中真正有价值的引擎能力
- 避免直接照搬旧项目的舆情 / 平台化外壳
- 默认围绕“小说角色、组织、关系、世界规则、变量、世界线”做领域建模
- 默认先做后端能力，再逐步做前端交互
- 所有 LLM 调用统一走全局设施面板的模块绑定，不再引入旧的单组 LLM 环境变量

## 默认优先级

1. 跑通上传小说种子 -> ontology / seed analysis
2. 跑通角色 / 势力 / 组织档案生成
3. 跑通世界线创建、变量注入、角色动作、角色对话与自动演化
4. 跑通作者工作流：Chapter Context Pack -> writer prompt -> candidate 审核
5. 跑通创作者剧情灵感生成
6. 再补更深的图谱查询与沉浸式交互

## Writer Workflow

当前推荐的作者主链不是直接读原始 JSON，而是走统一工作流：

1. 在 `/writer` 选择 `project_chapter` 或 `worldline_branch`
2. 后端通过 `POST /api/novel/chapter-context` 生成 `ChapterContextPack`
3. 作者先消费 `must_know / warnings / scene_candidates / writer_prompt_block`
4. 若 pack 中命中运行时候选记忆，可通过右侧审校面板读取 timeline
5. 对单条 candidate 执行 adopt / reject，随后原地刷新 pack

这里的默认原则是：

- 写作上下文默认 canon-first
- candidate 只在显式允许或审核视图中出现
- worldline 写作上下文必须同时参考 project canon，不能只看分支事件

## 当前关键入口

- README: [README.md](../README.md)
- 后端入口: [backend/run.py](../backend/run.py)
- Flask App: [backend/app/__init__.py](../backend/app/__init__.py)
- 项目 API: [backend/app/api/project.py](../backend/app/api/project.py)
- 小说 API: [backend/app/api/novel.py](../backend/app/api/novel.py)
- 世界线 API: [backend/app/api/worldline.py](../backend/app/api/worldline.py)
- 小说 ontology: [backend/app/services/story_ontology_generator.py](../backend/app/services/story_ontology_generator.py)
- 小说种子分析: [backend/app/services/novel_seed_analyzer.py](../backend/app/services/novel_seed_analyzer.py)
- 实体档案: [backend/app/services/narrative_entity_archivist.py](../backend/app/services/narrative_entity_archivist.py)
- 世界线引擎: [backend/app/services/worldline_engine.py](../backend/app/services/worldline_engine.py)
- 角色对话服务: [backend/app/services/character_agent_service.py](../backend/app/services/character_agent_service.py)
- 剧情灵感服务: [backend/app/services/plot_inspiration_engine.py](../backend/app/services/plot_inspiration_engine.py)

## 迁移判断

旧仓库中最值得保留的是：

- 文件解析
- 项目持久化
- Zep 图谱构建
- Zep 实体读取
- LLM 调用封装
- 报告与模拟的总体编排思路

旧仓库中不应原样搬入的是：

- Twitter / Reddit 外壳语义
- 舆情导向 ontology
- 过重的平台 UI 词汇
- 明显陈旧或有契约漂移的前端 API

## 下一阶段推荐动作

1. 接入真实图谱节点/边查询，让前端图谱从占位数据升级为真实关系图
2. 把角色对话从模板驱动升级为可选 LLM 驱动
3. 增加世界线 cast/agent 列表接口，降低前端手填角色名成本
4. 增加章节级事件抽取与事件回放
5. 增加剧情报告导出与当前世界阶段总结视图
6. 在拿到可用 `ZEP_API_KEY` 后补齐在线建图端到端验证
