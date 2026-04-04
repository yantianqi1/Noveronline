# Writer Workbench Timeline Log Panel

## Context

The Writer Workbench's "来源与日志" right panel has an "Agent 日志" section that displays a flat list of `{agent, message}` entries. The backend SSE stream sends rich structured events (tool_call with name+input, tool_result with name+summary, phase transitions), but the frontend collapses all of them into a single `orchestrator` badge + message string. Tool call inputs, results, timing, and agent reasoning are all lost.

The writer agent service uses a dual-layer architecture: an orchestrator agent (cheap model with tool-calling) collects context via 8 tools, then a writer agent (strong model) generates prose. The current log panel provides no visibility into this pipeline.

**Goal:** Replace the useless "Agent 日志" section with a compact terminal-style timeline log that shows every step of the agent pipeline: tool calls with human-readable descriptions, LLM thinking process, phase summaries, and streaming progress.

## Design

### Backend SSE Event Enrichment

**Files to modify:**
- `backend/app/services/writer_agent/agent_loop.py`
- `backend/app/services/writer_agent/orchestrator.py`
- `backend/app/services/writer_agent/tools.py`

#### Timing Infrastructure

`orchestrator.py` records `t0 = time.monotonic()` at the start of `run()`. Every yielded event gets two fields:

```python
"ts": time.strftime("%H:%M:%S"),          # HH:MM:SS local time
"elapsed_ms": int((time.monotonic() - t0) * 1000)  # ms since pipeline start
```

Exception: `writer_token` events are NOT enriched (too frequent, ~dozens per second).

#### Event Forwarding Change

Currently `orchestrator.py` wraps `tool_call` and `tool_result` events from `agent_loop` as `orchestrator_status` with phase="tool_call"/"tool_result". This loses structured data.

**Change:** Forward `tool_call`, `tool_result`, and new `thinking` events directly with their original types, only adding `ts` and `elapsed_ms`.

#### New Event: `thinking`

When the LLM returns `response.content` (reasoning text) alongside tool calls, yield:

```python
{"type": "thinking", "ts": "...", "elapsed_ms": ..., "content": "需要了解林黛玉的角色档案..."}
```

This is yielded in `agent_loop.py` after each LLM response that has both content and tool_calls.

#### New Event: `phase_summary`

Yielded by `orchestrator.py` after the agent loop completes (before writing phase):

```python
{"type": "phase_summary", "ts": "...", "elapsed_ms": ..., "phase": "collecting", "tool_count": 4, "message": "收集完成：4次工具调用，耗时2.6s"}
```

#### Tool Display Formatters

In `tools.py`, add a `TOOL_DISPLAY_FORMATTERS` dict that maps tool names to functions producing human-readable descriptions:

```python
TOOL_DISPLAY_FORMATTERS = {
    "query_entity": lambda inp: f"查询角色档案：{inp.get('name', '?')}",
    "query_relationship": lambda inp: f"查询关系：{inp.get('source', '?')} ↔ {inp.get('target', '?')}",
    "query_chapter": lambda inp: f"查询章节：第{inp.get('chapter_order', '?')}章",
    "query_scene": lambda inp: f"查询场景：{inp.get('scene_id', inp.get('chapter_id', '?'))}",
    "search_settings": lambda inp: f"搜索设定：{inp.get('query', '?')}",
    "get_recent_scenes": lambda inp: f"获取最近 {inp.get('count', 3)} 个场景",
    "get_world_state": lambda inp: "查询世界线状态",
    "get_open_threads": lambda inp: f"获取未解决伏笔（至第{inp.get('up_to_chapter', '?')}章）",
}
```

`agent_loop.py` uses this to add `display` field to `tool_call` events:

```python
from .tools import TOOL_DISPLAY_FORMATTERS
display_fn = TOOL_DISPLAY_FORMATTERS.get(tool_name)
display = display_fn(tool_input) if display_fn else tool_name
yield {"type": "tool_call", "name": tool_name, "input": tool_input, "display": display}
```

#### Complete Event Sequence

```
orchestrator_status  {phase:"starting", ts, elapsed_ms, message:"编排层启动中..."}
thinking             {ts, elapsed_ms, content:"需要了解林黛玉的角色档案..."}
tool_call            {ts, elapsed_ms, name:"query_entity", input:{...}, display:"查询角色档案：林黛玉"}
tool_result          {ts, elapsed_ms, name:"query_entity", summary:"林黛玉，贾府外孙女..."}
thinking             {ts, elapsed_ms, content:"还需要查询她和薛宝钗的关系..."}
tool_call            {ts, elapsed_ms, name:"query_relationship", input:{...}, display:"查询关系：林黛玉 ↔ 薛宝钗"}
tool_result          {ts, elapsed_ms, name:"query_relationship", summary:"表面和善..."}
phase_summary        {ts, elapsed_ms, phase:"collecting", tool_count:2, message:"收集完成：2次工具调用，耗时2.6s"}
orchestrator_status  {phase:"writing", ts, elapsed_ms, message:"写作层启动中..."}
writer_token         {token:"..."}  (no timestamp)
writer_token         {token:"..."}
done                 {ts, elapsed_ms, word_count:1234, scene_id:"..."}
```

### Frontend Timeline Log Component

**File to modify:** `frontend/src/views/WriterWorkbenchView.vue`

#### Data Model

Replace `agentLog = ref([])` with:

```js
const agentTimeline = ref([])
let timelineIdCounter = 0

// Entry structure:
{
  id: 0,                      // auto-increment
  type: "status" | "thinking" | "tool_call" | "tool_result" | "summary" | "writing" | "done" | "error",
  ts: "12:03:01",             // from backend
  elapsedMs: 1200,
  // type-specific fields:
  message: "...",             // status, summary, done, error
  content: "...",             // thinking
  name: "query_entity",      // tool_call, tool_result
  display: "查询角色：...",   // tool_call
  summary: "...",             // tool_result
  wordCount: 0,              // writing (live update)
}
```

#### Event Handler Rewrite

```js
onEvent(event) {
  if (event.type === "orchestrator_status") {
    draftPhase.value = event.phase === "writing" ? "writing" : "collecting";
    message.value = event.message || "编排中...";
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "status",
      ts: event.ts,
      elapsedMs: event.elapsed_ms,
      message: event.message,
    });
  } else if (event.type === "thinking") {
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "thinking",
      ts: event.ts,
      elapsedMs: event.elapsed_ms,
      content: event.content,
    });
  } else if (event.type === "tool_call") {
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "tool_call",
      ts: event.ts,
      elapsedMs: event.elapsed_ms,
      name: event.name,
      display: event.display || event.name,
    });
  } else if (event.type === "tool_result") {
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "tool_result",
      ts: event.ts,
      elapsedMs: event.elapsed_ms,
      name: event.name,
      summary: event.summary,
    });
  } else if (event.type === "phase_summary") {
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "summary",
      ts: event.ts,
      elapsedMs: event.elapsed_ms,
      message: event.message,
    });
  } else if (event.type === "writer_token") {
    draftPhase.value = "writing";
    agentSceneContent.value += (event.token || "");
    // Update or create writing entry (single line, updated in-place)
    const last = agentTimeline.value[agentTimeline.value.length - 1];
    if (last?.type === "writing") {
      last.wordCount = agentSceneContent.value.length;
    } else {
      agentTimeline.value.push({
        id: timelineIdCounter++,
        type: "writing",
        ts: event.ts || "",
        wordCount: agentSceneContent.value.length,
      });
    }
  } else if (event.type === "error") {
    error.value = event.message || "生成失败";
    agentTimeline.value.push({
      id: timelineIdCounter++,
      type: "error",
      ts: event.ts || "",
      message: event.message,
    });
  }
}
```

#### onDone Handler Addition

In the existing `onDone` callback, add a timeline entry:

```js
onDone(event) {
  agentStreaming.value = false;
  draftPhase.value = "done";
  const wc = event.word_count || agentSceneContent.value.length;
  message.value = `创作完成：${wc} 字`;
  agentTimeline.value.push({
    id: timelineIdCounter++,
    type: "done",
    ts: event.ts || "",
    elapsedMs: event.elapsed_ms,
    message: `${wc} 字`,
  });
  loadScenes();
}
```

#### Template (replaces "Agent 日志" section)

```vue
<section class="context-block">
  <div class="context-block-header">
    <h3 class="context-block-title title-ancient">Agent 时间线</h3>
  </div>
  <div v-if="!agentTimeline.length" class="review-hint">
    生成正文后，这里会显示 Agent 的实时工作流程。
  </div>
  <div v-else ref="timelineScrollRef" class="timeline-log">
    <div
      v-for="entry in agentTimeline"
      :key="entry.id"
      class="tl-line"
      :class="'tl-' + entry.type"
    >
      <span class="tl-ts">{{ entry.ts }}</span>
      <span class="tl-icon">{{ timelineIcon(entry.type) }}</span>
      <span class="tl-body">{{ timelineBody(entry) }}</span>
    </div>
  </div>
</section>
```

#### Rendering Rules

| type | icon | color class | body content |
|------|------|-------------|-------------|
| `status` | `●` | `tl-status` (copper) | `message` |
| `thinking` | `💭` | `tl-thinking` (dimmed gray, italic) | `content` truncated to 80 chars |
| `tool_call` | `↗` | `tl-tool-call` (blue) | `display` |
| `tool_result` | `↙` | `tl-tool-result` (muted green) | `name → summary` truncated to 60 chars |
| `summary` | `■` | `tl-summary` (copper, bold) | `message` |
| `writing` | `✍` | `tl-writing` (copper, pulse animation) | `streaming N 字` (live-updated) |
| `done` | `✓` | `tl-done` (green) | `创作完成 (Xs, N字)` |
| `error` | `✗` | `tl-error` (red) | `message` |

#### Helper Functions

```js
function timelineIcon(type) {
  const icons = {
    status: "●", thinking: "💭", tool_call: "↗", tool_result: "↙",
    summary: "■", writing: "✍", done: "✓", error: "✗",
  };
  return icons[type] || "·";
}

function timelineBody(entry) {
  switch (entry.type) {
    case "status": case "summary": case "error":
      return entry.message || "";
    case "thinking":
      return (entry.content || "").slice(0, 80) + (entry.content?.length > 80 ? "..." : "");
    case "tool_call":
      return entry.display || entry.name;
    case "tool_result": {
      const s = entry.summary || "";
      const truncated = s.length > 60 ? s.slice(0, 60) + "..." : s;
      return `${entry.name} → ${truncated}`;
    }
    case "writing":
      return `streaming ${entry.wordCount || 0} 字`;
    case "done":
      return `创作完成 (${((entry.elapsedMs || 0) / 1000).toFixed(1)}s, ${entry.message || "?"})`;

    default:
      return "";
  }
}
```

#### CSS

```css
.timeline-log {
  font-family: var(--font-mono, "SF Mono", "Fira Code", monospace);
  font-size: 12px;
  line-height: 1.4;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px 0;
}

.tl-line {
  display: flex;
  gap: 6px;
  padding: 1px 0;
  align-items: baseline;
}

.tl-ts {
  flex-shrink: 0;
  width: 60px;
  text-align: right;
  color: var(--color-muted, #888);
  font-size: 11px;
}

.tl-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
}

.tl-body {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Type-specific colors */
.tl-status .tl-icon  { color: var(--color-copper, #b87333); }
.tl-thinking .tl-body { color: #999; font-style: italic; }
.tl-tool-call .tl-icon { color: #6ea8fe; }
.tl-tool-call .tl-body { color: #6ea8fe; }
.tl-tool-result .tl-icon { color: #75b798; }
.tl-tool-result .tl-body { color: #adb5bd; }
.tl-summary .tl-body { color: var(--color-copper, #b87333); font-weight: 600; }
.tl-writing .tl-icon { animation: pulse 1.5s ease-in-out infinite; }
.tl-done .tl-icon { color: #75b798; }
.tl-done .tl-body { color: #75b798; }
.tl-error .tl-icon { color: #ea868f; }
.tl-error .tl-body { color: #ea868f; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

#### Auto-scroll Behavior

Use a `ref` on the scroll container and watch `agentTimeline.length`:

```js
const timelineScrollRef = ref(null);
watch(() => agentTimeline.value.length, () => {
  nextTick(() => {
    const el = timelineScrollRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
});
```

#### Reset on New Generation

In `handleAgentGenerate()`, reset timeline before starting:

```js
agentTimeline.value = [];
timelineIdCounter = 0;
```

## Verification

1. **Backend unit test:** Start backend, trigger `/api/writer-agent/run` with a test project. Verify SSE events contain `ts`, `elapsed_ms`, `display`, `thinking` events, and `phase_summary`.

2. **Frontend visual test:** Open Writer Workbench, run a generation task. Verify:
   - Timeline shows all event types with correct icons and colors
   - Tool calls show human-readable descriptions (not raw function names)
   - Thinking events appear in gray italic
   - Writing line updates in-place with word count
   - Phase summary appears before writing phase
   - Auto-scroll works
   - Done line shows total time and word count

3. **Build validation:** `cd frontend && npm run build` passes without errors.
