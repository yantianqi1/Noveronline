# Async Seed Upload And Chapter Continuity Design

**Goal:** 把小说上传入口改成“快速返回 + 后台分析”的异步流水线，并在 LLM 分析前增加“章节切分 + 连续性摘要”中间层，让长篇小说也能稳定完成首轮分析。

**Recommended Approach:** 保留现有上传入口 `/api/project/seed/extract`，但改成只负责保存文件、创建项目和创建后台任务，真正的正文解析、章节切分、连续性摘要、种子分析与 ontology 生成放到后台线程执行。前端改为轮询任务状态并展示分阶段进度。

## Why This Approach

- 当前同步接口在 18MB 级别长文本上会卡超过 180 秒，用户会误判为上传失败。
- 章节切分与连续性摘要能把“大模型直接吃整本小说”的做法改成“先压缩结构，再做推理”，稳定性更高。
- 现有仓库已经有 `TaskManager` 与后台线程模式，可直接复用，不需要引入新的队列基础设施。

## Scope

这一轮要完成：

- `seed/extract` 改成异步
- 新增上传分析任务状态
- 新增章节切分服务
- 新增章节连续性摘要产物
- 前端上传后轮询任务并展示阶段进度
- 用《赘婿》做真实端到端验证

这一轮不做：

- 持久化任务队列
- 多机分布式任务执行
- 章节级复杂向量索引
- 章节切分的人工校正工作台

## Backend Design

### 1. Async Upload Contract

`POST /api/project/seed/extract`

立即返回：

- `project_id`
- `task_id`
- `status: processing`
- `message`

该接口只做：

- 校验表单
- 保存上传文件
- 创建项目
- 保存原始提取文本
- 创建后台任务并启动线程

### 2. Background Pipeline

后台任务阶段：

1. `extract_text`
2. `segment_chapters`
3. `build_continuity`
4. `seed_analysis`
5. `ontology`
6. `finalize`

每个阶段都回写：

- `progress`
- `message`
- `progress_detail.stage`
- `progress_detail.stage_label`

### 3. Chapter Segmentation

新增 `novel_chapter_segmenter` 服务：

- 优先识别 `第X章`、`第X回`、`卷X`、`幕X`
- 其次识别明显的标题行
- 如果正文没有稳定章标题，则按段落聚合成叙事块

输出每个章节块：

- `chapter_id`
- `title`
- `order`
- `content`
- `word_count`
- `source_range`

### 4. Continuity Summary

新增 `chapter_continuity_service`：

对每个章节块生成：

- `head_context`
- `core_conflicts`
- `key_characters`
- `key_organizations`
- `tail_hooks`
- `continuity_summary`

离线模式下用规则生成。
LLM 模式下对章节摘要分批生成，但不再直接喂整本正文。

### 5. LLM Input Strategy

ontology / 后续小说分析优先使用：

- 全局文本摘要
- 章节索引
- 章节连续性摘要
- 必要章节正文窗口

这样既减少 token 压力，也保住剧情连续性。

## Frontend Design

上传面板继续保留拖拽入口，但行为改成：

- 文件上传完成后立即显示“后台分析中”
- 展示当前阶段与总进度
- 通过 `task_id` 轮询任务接口
- 任务完成后自动刷新项目列表并切换到新 `project_id`

顶部全局状态条继续保留，用于跨页面观察后台分析进度。

## Data Artifacts

项目目录新增：

- `chapter_segments.json`
- `chapter_continuity.json`

项目状态增加中间态，例如：

- `seed_processing`
- `seed_completed`

## Testing

后端测试覆盖：

- `seed/extract` 立即返回 task
- 后台任务最终产出 `seed_analysis.json`
- `chapter_segments.json` 正常生成
- `chapter_continuity.json` 正常生成且包含连续性字段

前端验证：

- 构建通过
- 任务轮询正常
- 切换侧栏不丢进度

端到端验证：

- 用《赘婿》真实上传
- 确认项目能进入最终完成态，而不是卡死在同步请求里
