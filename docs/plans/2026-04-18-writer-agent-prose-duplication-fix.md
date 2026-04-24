# Writer Agent 正文重复显示 + 上下文污染修复计划

**创建**: 2026-04-18
**作者**: 诊断会话（前一轮）
**状态**: 待执行

## 0. 背景 / 立即需要知道的事

用户反馈写作台生成的正文出现大段规律性重复：

```
教坊司的门槛比陈府的石阶要高出三分教坊司的门槛比陈府的石阶要高出三分，漆成暗沉的赭红色…
齐斟悟走在前面，漆成暗沉的赭红色，踩上去没有半点声响。
齐斟悟走在前面，绛紫色的圆领袍袖口扫过长廊两侧的青铜灯架。他回过头，压，绛紫色的圆领袍袖口扫过长廊两侧的青铜灯架。他回过头，压低声音对陈迹笑道…
```

**经过诊断，正文重复不是 agent 写出来的，也不是 DB 出错。**
- DB 中 `scenes.sc_299bd2c73715.content` 长度 1674 字，**完全干净**，无重复。
- 屏幕上显示的约 3000+ 字，呈 "chunk A / chunk A 重复 / chunk B / chunk B 重复" 节拍。
- 后端只有一处发 `writer_token`（`orchestrator.py:330`），每个 LLM chunk 只发一次；`compose_stream` 是标准 OpenAI delta。
- **根因**：前端 `setAgentTrace((prev) => { ... })` 的 updater 里有副作用 `contentRef.current += token`，而 `main.tsx:8` 启用了 React 19 `<StrictMode>`。StrictMode 会故意双跑 state updater 来揭露不纯函数，导致每个 token 被追加两遍。

除此之外，调查过程发现 3 个影响"agent 收集信息质量"的次要问题，一并修复。

## 1. 先读这些文件（开工前的上下文）

以下文件是本次修复的主战场，新会话先读这几个文件的当前内容（不是 HEAD，是工作区未提交版本）：

- `frontend/src/pages/writer/use-writer-state.ts` — handleTraceEvent 在这里
- `frontend/src/main.tsx` — 确认 StrictMode 仍启用（不要改这里）
- `backend/app/services/writer_agent/orchestrator.py` — 收集/编排/写作/审校的入口，tool_results_raw 聚合也在这
- `backend/app/services/writer_agent/tool_executors.py` — `_query_entity` 里有 entity 字段 + 正典档案字段重叠
- `backend/app/api_fastapi/writer_agent.py` — `/apply-reviewer` 端点在这
- `backend/app/services/writer_agent/writer.py` — 只读；确认 composer 如何渲染 `_tool_results` 和 `dedup_constraints`
- `backend/app/repositories/scene_repo.py` — `get_scene` 已存在，任务 D 会用
- `backend/app/services/writer_agent/agent_loop.py` — 只读；tool_call 事件携带 `name` + `input`（args 字典），任务 B 去重需要

`git status` 会显示 `backend/app/services/writer_agent/` 下一批未提交改动。这些改动是上一轮添加 reviewer / dedup_extractor / anti-cliche / keepalive 的产物，**本次修复与它们共存，不要回退**。

## 2. 任务清单

按执行顺序给出。A 是所有人肉眼可见问题的唯一根因，必须先做并验证。B/C/D 独立、可并行。E 是设计调整，默认暂缓。

---

### A. 修复 StrictMode 下 writer_token 双重累加（必修，最高优先级）

**症状**：屏幕上正文每段有节奏地重复。
**根因**：`setAgentTrace((prev) => { ... })` 的 updater 在 `writer_token` 分支里直接写外部 ref + 调其它 setState，副作用在 StrictMode 下被跑两次。

**文件**: `frontend/src/pages/writer/use-writer-state.ts`

**当前代码**（约 432-436 行，在 `handleTraceEvent` 里）：
```ts
} else if (event.type === "writer_token") {
  setDraftPhase("writing");
  contentRef.current += (event.token as string) || "";
  setAgentSceneContent(contentRef.current);
  next.writer = { ...prev.writer, status: "running", wordCount: contentRef.current.length };
}
```

**改法**：把 `writer_token` 分支整段从 `setAgentTrace` 的 updater 里提到外面，在进入 `setAgentTrace` 之前处理。updater 内只保留纯变换。

```ts
const handleTraceEvent = useCallback(
  (event: SSEEvent) => {
    // writer_token 走独立路径：ref 累加 + setState 在 reducer 外做，updater 必须纯。
    if (event.type === "writer_token") {
      const token = (event.token as string) || "";
      contentRef.current += token;
      setAgentSceneContent(contentRef.current);
      setDraftPhase("writing");
      const wc = contentRef.current.length;
      setAgentTrace((prev) => ({
        ...prev,
        writer: { ...prev.writer, status: "running", wordCount: wc },
      }));
      return;
    }

    setAgentTrace((prev) => {
      const next = { ...prev };
      // ...原有分支保留，但删掉 writer_token 分支，删掉嵌套的 setDraftPhase/setMessage/setError/setAgentStreaming
      return next;
    });
  },
  [ensureRound],
);
```

**同时**：把 updater 里剩下的嵌套 setState 也挪出去（StrictMode 对它们一样会双跑）：
- `orchestrator_status` 分支的 `setDraftPhase(...)`、`setMessage(...)` → 提到 `setAgentTrace` 之前
- `outline_ready` 分支的 `setDraftPhase("done")` 和 `setOutlineData(...)` → 提到外面
- `error` 分支的 `setError(...)`、`setAgentStreaming(false)`、`setDraftPhase(...)` → 提到外面

改完后 `setAgentTrace((prev) => { ... })` 的 updater **只做纯变换** `prev → next`，不 mutate 任何 ref、不调任何其它 setState。

**验证**：
1. `cd frontend && npm run dev` 起前端，后端跑着。
2. 写作台生成一个场景，等流完。
3. 肉眼看屏幕正文：不应再有任何连续重复段。
4. 同一 scene 的 `sqlite3 backend/data/mirofish.db "SELECT length(content) FROM scenes WHERE scene_id='<...>'"` 长度应与屏幕显示字数一致（之前屏幕约为 DB 的 2x）。
5. 浏览器 devtools Network 面板查 `/api/writer-agent/run` 响应，计数 `writer_token` 事件数和 token 文本总长，应等于 `full_text` 长度、等于 DB 内容长度。

**风险**：较低。只是重构 handleTraceEvent 的结构，原功能行为不变（除了去掉错误双跑）。如果有 TypeScript 编译错误（`next.writer` 在 writer_token 分支里不再存在），按新结构调整。

---

### B. `_tool_results` 去重（次要，5-10 行）

**症状**：同一轮如果 orchestrator agent 对同一工具调用多次（如 `query_entity("陈迹")` 被重复调用），写作层 prompt 里被塞入同样的原始结果多份，token 浪费 + 可能让 LLM 把重复当成强调信号。

**文件**: `backend/app/services/writer_agent/orchestrator.py`

**当前代码**（约 161-172 行）：
```python
tool_results_raw: list[dict] = []  # Collect raw tool outputs
async for event in agent_loop.run(user_msg):
    ...
    elif event["type"] in ("tool_call", "tool_result", "thinking", "prompt_snapshot"):
        if event["type"] == "tool_call":
            tool_count += 1
        if event["type"] == "tool_result":
            tool_results_raw.append({
                "tool": event.get("name", ""),
                "result": event.get("full_result", event.get("summary", "")),
            })
        yield event
```

**改法**：`agent_loop` 的 `tool_call` 事件会先发，带 `name` + `input`（参数字典）。暂存 `tool_input`，在对应 `tool_result` 到来时按 `(name, json.dumps(input, sort_keys=True, ensure_ascii=False))` 作为 key 去重。

```python
tool_results_raw: list[dict] = []
_pending_tool_inputs: dict[str, dict] = {}   # 以 name+input 为 key 暂存，tool_result 到来时匹配
_seen_tool_keys: set[str] = set()

async for event in agent_loop.run(user_msg):
    if event["type"] == "brief_ready":
        brief_content = event.get("content", "")
    elif event["type"] in ("tool_call", "tool_result", "thinking", "prompt_snapshot"):
        if event["type"] == "tool_call":
            tool_count += 1
            key = _make_tool_key(event.get("name", ""), event.get("input") or {})
            _pending_tool_inputs[key] = event.get("input") or {}
        if event["type"] == "tool_result":
            name = event.get("name", "")
            # tool_result 事件没有 input 字段，用 name 查最近一条匹配的 input 不靠谱；
            # 更稳的做法是在 tool_call 到来时就建 dedup key，tool_result 复用最近未消费的 key
            # 简化方案：按 (tool, result_text 前 256 字符) 作为 key 去重（抗同 tool 不同 args 的误去重）。
            result = event.get("full_result", event.get("summary", ""))
            fingerprint = f"{name}::{(result or '')[:256]}"
            if fingerprint not in _seen_tool_keys:
                _seen_tool_keys.add(fingerprint)
                tool_results_raw.append({"tool": name, "result": result})
        yield event
    elif event["type"] == "error":
        yield event
        return
```

**实现要点**：
- `tool_result` 事件**不带 `input`**，所以用 `(tool_name, result前256字符)` 作为 fingerprint 最干净、最能抗误去重（不同 args 下结果通常不同）。
- 仍然 `yield event` 给前端，去重只影响 `_tool_results` 数组（注入给 writer 的那份）。前端 trace 面板仍然显示所有 tool_call。

**验证**：
- 有条件时在前端用一条明显会触发重复 tool 调用的指令（如 "根据陈迹的所有档案写一段"，agent 可能连调 `query_entity("陈迹")` 多次）。
- 打开 writer prompt_snapshot 事件看 `### 参考资料` 段落；改前每个重复 tool 结果各一份，改后只一份。
- 后端日志里加一个 `logger.info("tool_results dedup: raw=%d, unique=%d", ...)` 观察。

---

### C. `_query_entity` 折叠 entity/canon 字段重叠（次要）

**症状**：`_query_entity` 先输出 entity 行的结构化字段（核心驱动/表面伪装/内在矛盾/说话风格等），再输出一段"正典档案"，两者同字段时重复。

**文件**: `backend/app/services/writer_agent/tool_executors.py`

**当前代码**（`_query_entity` 函数，已在最近 diff 中新增了"正典档案"段落）：
```python
if merged is not None and merged.canon_profile:
    cp = merged.canon_profile
    canon_lines = [
        "",
        "===== 正典档案（来自档案库，与上面结构化字段冲突时以此为准）=====",
    ]
    _append_if(canon_lines, "身份定位", cp.get("entity_role"))
    _append_if(canon_lines, "正典·核心驱动", cp.get("core_drive"))
    _append_if(canon_lines, "正典·表面伪装", cp.get("surface_mask"))
    _append_if(canon_lines, "正典·深层张力", cp.get("hidden_tension"))
    _append_if(canon_lines, "正典·关系概述", cp.get("relationship_summary"))
    _append_if(canon_lines, "Agent 行为提示", cp.get("agent_behavior_hint"))
    _append_if(canon_lines, "正典·风险清单", _pretty_json(cp.get("notable_risks_json")))
    if len(canon_lines) > 2:
        canon_lines.append("===== 正典档案结束 =====")
        lines.extend(canon_lines)
```

**改法**：canon 字段逐一比对 entity 行同名字段，**值相同时跳过**；只输出 "canon 独占" 的字段（如 `relationship_summary`、`agent_behavior_hint`、`notable_risks_json`）或与 entity 不同的字段。注释里明确说明取舍逻辑。

```python
if merged is not None and merged.canon_profile:
    cp = merged.canon_profile
    canon_lines: list[str] = []

    def _maybe(label: str, canon_val, entity_field: str | None = None):
        if not canon_val:
            return
        # 与上方 entity 结构化字段相同则不重复输出
        if entity_field and (entity.get(entity_field) or "") == canon_val:
            return
        canon_lines.append(f"{label}：{canon_val}")

    _maybe("身份定位", cp.get("entity_role"), "entity_role")
    _maybe("正典·核心驱动", cp.get("core_drive"), "core_drive")
    _maybe("正典·表面伪装", cp.get("surface_mask"), "surface_mask")
    _maybe("正典·深层张力", cp.get("hidden_tension"), "hidden_tension")
    # 下面三项 entity 行没有对应列，canon 独占，直接追加
    if cp.get("relationship_summary"):
        canon_lines.append(f"正典·关系概述：{cp['relationship_summary']}")
    if cp.get("agent_behavior_hint"):
        canon_lines.append(f"Agent 行为提示：{cp['agent_behavior_hint']}")
    notable = _pretty_json(cp.get("notable_risks_json"))
    if notable:
        canon_lines.append(f"正典·风险清单：{notable}")

    if canon_lines:
        lines.append("")
        lines.append("===== 正典档案（与上面重叠的字段已折叠，此处仅列 canon 独有或与 entity 不一致的部分）=====")
        lines.extend(canon_lines)
        lines.append("===== 正典档案结束 =====")
```

**验证**：
- 找一个 entity 行和 canon 字段都有完整内容的角色（`陈迹` 之类），手动跑 `query_entity` tool（或让 writer agent 生成一次），看 prompt_snapshot 里 `query_entity` 返回是否变短。
- 找一个 entity 行缺失但 canon 有的角色，确认 canon 独占字段仍能输出。
- 注意 `_format_archive_only`（archive-only fallback 分支）不要动，它是 canon-only 的场景。

---

### D. `/apply-reviewer` 从 DB 读回 `writing_brief`（次要）

**症状**：用户点 "采纳审校建议" 触发改写时，前端发 `writing_brief: {}`（见 `use-writer-state.ts:1161` 的 `writing_brief: {}` 注释 `// server falls back to its stored brief via scene repo (not yet wired)`）。服务端就用空 brief 去驱动 composer，人设/关系/设定/反套路全部丢失，改写质量明显低于初稿。

**文件**:
- `backend/app/api_fastapi/writer_agent.py`（`apply_reviewer` 端点）
- `backend/app/services/writer_agent/post_processor.py`（确认 `writing_brief_json` 的持久化路径）

**改法**：
1. `PostProcessor.process` 当前是否把 `writing_brief` 写入 `scenes.writing_brief_json`？先读代码确认；如果还没写，补一句 `values["writing_brief_json"] = json.dumps(writing_brief, ensure_ascii=False)`。
2. `apply_reviewer` 里：若客户端传来的 `writing_brief` 为空（或缺关键字段如 `pov`/`involved_characters`），从 `SceneRepository(get_engine()).get_scene(project_id, scene_id)` 读回 `writing_brief_json`，解析后用作基底；再叠加改写 constraints 和 `original_text`。

```python
# 在 apply_reviewer 里，解析完 payload 后：
writing_brief = dict(payload.get("writing_brief") or {})
if not writing_brief or not writing_brief.get("pov"):
    from app.repositories.scene_repo import SceneRepository
    scene_row = SceneRepository(_get_engine()).get_scene(project_id, scene_id)
    if scene_row and scene_row.get("writing_brief_json"):
        try:
            stored = json.loads(scene_row["writing_brief_json"])
            if isinstance(stored, dict):
                # stored 做基底，前端传进来的覆盖 stored（允许前端补字段）
                merged = {**stored, **writing_brief}
                writing_brief = merged
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse stored writing_brief_json for %s", scene_id)
```

**验证**：
1. 初稿跑一次，落库得到 `scene_id` + `writing_brief_json`。
2. 点 "审校建议 → 采纳 + 改写"。
3. 在 `/apply-reviewer` 端点添加一个 `logger.info("apply_reviewer brief keys: %s", list(writing_brief.keys()))`，观察是否拿到了 `pov` / `involved_characters` / `relationships` 等字段。
4. 改写结果应保持 POV 语气和人设。

---

### E. Reviewer 时机（设计调整，默认暂缓）

**当前流程**：
```
orchestrator → writer → PostProcessor(落库) → DedupExtractor(后台) → Reviewer → done
```

**观察到的问题**：
- 劣质初稿已经进了 `scenes` 表。
- `DedupExtractor` 从劣质稿里提取 "反重复清单"，污染下一章约束。
- 用户只能事后按 "采纳改写" upsert 覆盖。

**可选方案**（若决定做才动手）：
1. 让 `orchestrator.run` 返回 `reviewer_feedback` 后**不自动落库**，改发 `awaiting_commit` 事件。
2. 前端根据 reviewer feedback 显示 "采用初稿入库 / 采纳建议改写 / 丢弃"。
3. 新增 `/api/writer-agent/commit-scene` 端点接收 "采用初稿 + scene_id + content + writing_brief"，走一遍 PostProcessor + DedupExtractor。
4. 若用户选 "采纳建议改写"，走 `/apply-reviewer`（此端点内部已经会落库，可以 keep as-is）。

这动到用户流程，建议和用户确认再做。**本次 A-D 做完就可以先上线验证。**

---

## 3. 执行顺序 / 提交节奏

建议拆成 4 次提交：

1. `fix(frontend): move writer_token side effects out of setAgentTrace reducer`（任务 A）
2. `feat(writer): dedupe orchestrator _tool_results injected into composer`（任务 B）
3. `refactor(writer): collapse entity/canon field duplication in query_entity`（任务 C）
4. `fix(writer-agent): apply-reviewer falls back to scene.writing_brief_json when client brief is empty`（任务 D）

每一步独立、可回滚、可验证。做完一个就手动 QA 一次。

## 4. 不要做

- 不要改 `main.tsx` 关 StrictMode。StrictMode 正在揭露代码里的真实 bug，关掉它只会让 bug 在生产里继续存在（React 19 在并发模式下也会双跑 updater）。
- 不要回退 `keepalive`、`reviewer`、`dedup_extractor`、`anti_cliche` 这些新加的功能——它们独立、与本次修复不冲突。
- 不要触碰 alembic 下的 schema；本次修复不涉及新列。
- 不要改 `scenes` 表 UNIQUE 约束或 PostProcessor 的 `_resolve_scene_order`（那个已经是之前加的修复）。

## 5. 完成的判据

- [ ] 前端生成一个 500+ 字的场景，屏幕显示内容**长度等于 `sqlite3 scenes.content` 的长度**，无连续重复段。
- [ ] prompt_snapshot 事件里的 `### 参考资料` 段落不再出现同 tool 同 fingerprint 的重复块。
- [ ] `query_entity` 结果文本在 entity 与 canon 字段完全同值时，不再输出重复的 "核心驱动/正典·核心驱动" 这类对字段。
- [ ] 点 "采纳审校建议" 后，服务端日志里 `apply_reviewer brief keys` 包含 `pov` 等关键字段；改写结果保持 POV 语气。
- [ ] 所有既有测试仍通过：`cd backend && PYTHONPATH=$(pwd) uv run pytest tests/` 绿；`cd frontend && npm run lint` 绿。
