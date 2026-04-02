# 第一阶段小说文本提示词汇总
更新时间：2026-03-30

本文档汇总 `backend/app/services/seed_extract_runner.py` 这条第一阶段主链里实际发给 LLM 的提示词。
完整阶段顺序：`extract_text -> segment_chapters -> skeleton_timeline -> build_blocks -> anchor_generation -> extract_local_facts -> merge_story_memory -> entity_resolution -> contextual_block_analysis -> chapter_card_generation -> consistency_audit -> build_continuity -> seed_analysis -> ontology`
真正有提示词的阶段只有 6 个：`anchor_generation`、`extract_local_facts`、`entity_resolution`、`contextual_block_analysis`、`chapter_card_generation`、`ontology`
不走 LLM 的阶段：`extract_text`、`segment_chapters`、`skeleton_timeline`、`build_blocks`、`merge_story_memory`、`consistency_audit`、`build_continuity`、`seed_analysis`
为控制单文件行数，下面按源码内容做等价压缩排版，只压缩空行和 JSON 示例换行，语义与字段不变。

## 1. anchor_generation
源码：`backend/app/services/anchor_point_prompts.py`、`backend/app/services/anchor_point_builder.py`

System Prompt
```text
你是一名小说世界状态追踪分析师。
请根据前一个锚点的世界状态、当前区间章节指纹和关键段落，输出当前区间结束后的世界状态。
你必须直接输出严格有效的 JSON，不要输出任何额外解释。
JSON 结构：
{
  "world_state": {
    "active_characters": [{"name": "角色名", "status": "active|dead|injured|missing", "last_action": "最近动作"}],
    "active_organizations": [{"name": "组织名", "status": "当前状态", "key_change": "关键变化"}],
    "key_relationships": [{"source": "实体A", "target": "实体B", "state": "关系状态", "since_chapter": 1}],
    "open_plot_threads": ["仍未解决的线索"],
    "recent_events_summary": "当前区间的重要剧情摘要"
  }
}
要求：
- 只保留对后续块理解最关键的状态
- 若证据不足，不要臆测
- recent_events_summary 使用中文简洁概括
```

User Prompt 模板
```text
## 前一个锚点的世界状态
{previous_state}
## 当前区间章节指纹
{chapter_fingerprint_lines_or_无}
## 当前区间关键段落
{chapter_snippets_or_无}
```

拼装来源：`previous_state` 直接插入上一个锚点的世界状态 dict；章节指纹每行格式为 `{title}: {fingerprint} 尾钩: {tail_hook}`；关键段落每行格式为 `{title}: {首句；尾句}`

## 2. extract_local_facts
源码：`backend/app/services/local_block_fact_prompts.py`、`backend/app/services/local_block_fact_extractor.py`、`backend/app/services/local_block_fact_support.py`
该阶段 user prompt 通过 `PromptBudgetManager` 拼装，默认 section 顺序：骨架角色列表、锚点世界状态、章节指纹、主块正文、上下文章节。

System Prompt
```text
你是一名小说块级事实抽取器。
只抽取当前主块章节中可以明确证实的事实，不要脑补前文，不要把上下文章节中的事实算入主块正式输出。上下文章节只用来帮助理解边界剧情。
你必须直接输出严格有效的 JSON 对象，不要输出任何额外解释、不要用 markdown 代码块包裹。
JSON 结构必须严格遵循以下示例格式：
{
  "local_events": [{"event_id": "ch01_event_01", "chapter_id": "ch01", "summary": "事件简述，不超过180字", "characters": ["角色名A", "角色名B"], "organizations": ["组织名"], "evidence": ["原文摘录片段1", "原文摘录片段2"]}],
  "local_entities": [{"name": "实体名", "entity_type": "character 或 organization", "aliases": ["别名1"], "summary": "该实体在本块中的表现概述", "importance_tier": "protagonist 或 major 或 supporting 或 minor", "evidence": ["原文佐证"]}],
  "local_relationship_changes": [{"source": "实体A", "target": "实体B", "change": "ally 或 conflict 或 co_occurrence", "weight": 1, "evidence": ["关系佐证原文"]}],
  "local_threads": [{"thread_key": "线索关键词（不超过40字）", "status": "open 或 closed", "summary": "线索描述"}],
  "unresolved_refs": [{"alias": "未解析的指代", "candidate_names": ["可能指代的角色A", "可能指代的角色B"], "reason": "说明为何无法确定"}],
  "local_summary": "当前块的一句话主线概括",
  "evidence_spans": [{"chapter_id": "ch01", "snippet": "关键原文摘录片段，不超过180字"}]
}
```

User Prompt 模板
```text
## 全文角色/组织骨架（正则预扫描结果，供参考）
{skeleton_context}
block_id: {block_id}
owned_chapters: {owned_chapter_ids}
context_chapters: {context_chapter_ids}
## 前情锚点摘要
{anchor_context}
## 前文块章节指纹
{fingerprint_context}
## 主块正文
{owned_text}
## 上下文章节
{context_text_or_无}
```

拼装来源：`skeleton_context` 来自全文角色/组织频率和当前块覆盖范围；`anchor_context` 来自最近锚点的活跃角色、组织、关系、线索、最近事件；`fingerprint_context` 取前 2 个块的章节指纹；`owned_text` 与 `context_text_or_无` 都按 `### 章节名 + 正文` 拼接

## 3. entity_resolution
源码：`backend/app/services/entity_resolution_prompts.py`、`backend/app/services/entity_resolution_service.py`
这是成对实体判定 prompt，不是整本小说一次性总 prompt。

System Prompt
```text
你是一名小说实体消歧专家。
给定两个候选实体的名字、类型、摘要、证据和出现位置，判断它们是否是同一个角色或组织。
你必须直接输出严格有效的 JSON：
{"merge": true, "canonical_name": "保留的标准名称", "reason": "简短判断依据"}
规则：
- 若证据不足，输出 merge: false
- 若 entity_type 不同，输出 merge: false
- 不要只因为名字相似就合并
```

User Prompt 模板
```text
候选匹配类型：{match_type}
实体A：{name_a}
类型：{entity_a.entity_type}
摘要：{entity_a.summary}
证据：{entity_a.evidence[:3]}
出现块：{entity_a.mention_blocks}
实体B：{name_b}
类型：{entity_b.entity_type}
摘要：{entity_b.summary}
证据：{entity_b.evidence[:3]}
出现块：{entity_b.mention_blocks}
```

拼装来源：`match_type` 目前来自 `substring` 或 `typo`；证据与出现块都直接取实体注册表的当前聚合结果

## 4. contextual_block_analysis
源码：`backend/app/services/contextual_block_analyzer.py`
该阶段 user prompt 同样通过 `PromptBudgetManager` 拼装，默认 section 顺序：前情快照、块内事实、主块正文、边界上下文。

System Prompt
```text
你是一名小说结构分析师。
请基于"前情快照 + 当前主块正文 + 边界上下文"分析当前块，只输出主块章节的最终判断。
你必须直接输出严格有效的 JSON 对象，不要输出任何额外解释、不要用 markdown 代码块包裹。
JSON 结构必须严格遵循以下示例格式：
{
  "plot_summary": "承接前情与当前块的剧情概要",
  "character_state_updates": [{"name": "角色名", "state": "active 或 dead 或 injured 或 missing", "evidence": ["状态佐证原文"]}],
  "relationship_updates": [{"source": "实体A", "target": "实体B", "state": "ally 或 conflict 或 co_occurrence", "evidence": ["关系变化佐证原文"]}],
  "thread_updates": [{"thread_key": "线索关键词", "status": "open 或 closed 或 progressed", "summary": "线索进展描述"}],
  "block_end_state": {"focus_characters": ["核心角色A", "核心角色B"], "focus_organizations": ["核心组织"], "open_threads": ["未关闭的线索1", "未关闭的线索2"], "summary": "块结束时的整体态势概括"}
}
```

User Prompt 模板
```text
block_id: {block_id}
## 前情快照
{snapshot_json}
## 局部事实
{packet_json}
## 主块正文
{owned_text}
## 边界上下文
{context_text_or_无}
```

拼装来源：`snapshot_json` 与 `packet_json` 都是 `json.dumps(..., ensure_ascii=False)` 后插入；正文与边界上下文都按章节正文拼接

## 5. chapter_card_generation
源码：`backend/app/services/chapter_card_generator.py`

System Prompt
```text
你是一名小说章节分析师。
请基于当前章节正文、已有前情摘要、故事记忆与块分析，输出严格有效的 JSON 对象。不要输出 markdown，不要输出解释，不要省略字段。
JSON 结构必须如下：
{
  "summary_text": "中文，100-220字，概括本章核心推进",
  "start_anchor": "中文，本章开场承接点",
  "end_anchor": "中文，本章结尾留给下一章的承接点",
  "key_events": [{"summary": "中文，关键事件"}],
  "open_threads": [{"thread_key": "线索键", "summary": "中文，未收束线索"}],
  "character_state_updates": [{"name": "角色名", "state": "active/dead/injured/missing", "summary": "中文，状态变化"}],
  "relationship_updates": [{"source": "实体A", "target": "实体B", "state": "ally/conflict/co_occurrence", "summary": "中文，关系变化"}],
  "timeline_note": "中文，时间线注记",
  "key_entities": [{"name": "实体名", "entity_type": "character/organization/location/artifact/other"}]
}
```

User Prompt 模板
```text
chapter_id: {chapter_id}
chapter_order: {chapter_order}
title: {title}
## 当前章节正文
{chapter_content}
## 最近章节卡
{prior_cards[-3:]}
## 到当前章为止的故事事件
{history_events[:6]}
## 到当前章为止的未解线索
{history_threads[:6]}
## 世界规则
{story_memory.world_rules}
## 当前章节相关块分析
{block_context}
```

拼装来源：`prior_cards` 只取最近 3 章卡片；`history_events` 和 `history_threads` 各取到当前章为止的前 6 项；`block_context` 取当前章节所属剧情块的分析结果；这些内容直接插入 Python 列表/字典字面量，不做 pretty JSON

## 6. ontology
源码：`backend/app/services/story_ontology_generator.py`、`backend/app/services/story_context_source_builder.py`

System Prompt
```text
你是一位专业的小说结构分析师、世界观建模师和叙事图谱设计专家。
你的任务是分析给定的小说文本、设定和创作目标，设计一个适合“故事演化模拟”的本体。
你必须输出严格有效的 JSON，不要输出任何额外说明。
## 系统目标
这个系统不是做舆情分析，而是做：
- 角色关系演化
- 组织 / 阵营 / 势力博弈
- 剧情分支推演
- 人机关系演化
- 平行世界变量注入
## 实体类型设计原则
优先覆盖以下对象：
- 有名字的人物
- AI / 系统 / 机械生命 / 数字意识
- 组织、宗门、公司、团体、势力、流派
- 地点、重要物件、规则系统
- 情节事件、冲突、目标、关系弧线
输出结构：
{
  "entity_types": [{"name": "PascalCase", "description": "英文简短描述", "attributes": [{"name": "snake_case", "type": "text", "description": "属性说明"}], "examples": ["示例1", "示例2"]}],
  "edge_types": [{"name": "UPPER_SNAKE_CASE", "description": "英文简短描述", "source_targets": [{"source": "源实体类型", "target": "目标实体类型"}], "attributes": []}],
  "analysis_summary": "中文总结",
  "story_focus": ["该小说最值得追踪的叙事主轴1", "该小说最值得追踪的叙事主轴2"]
}
约束：
- entity_types 输出 6-10 个
- edge_types 输出 6-10 个
- 必须包含 Character / Organization / Faction / PlotEvent 这类叙事核心类型，名称可细化
- 如果文本里有 AI、系统、机械、数字意识，必须专门设计对应实体类型
- 不要把纯抽象概念当成唯一核心实体，抽象概念更适合变成属性、事件或关系背景
```

User Prompt 模板
```text
## 小说材料
{llm_source}
## 分析目标
{analysis_goal}
## 额外说明
{additional_context}
```

拼装来源：`llm_source` 优先级是 `story_memory + block_analyses` 的结构化摘要，其次是 `chapter_continuity`，最后才回退到原始全文；`additional_context` 只有在传入时才追加这一节
