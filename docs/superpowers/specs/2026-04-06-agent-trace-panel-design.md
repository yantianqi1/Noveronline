# Agent Trace Panel Redesign

## Context

The writer workbench's "Agent Timeline" log display is engineer-oriented and unfriendly:
- All events (tool_call, tool_result, thinking, prompt_snapshot) are flat in a single monospace list
- tool_result truncated to 60 chars, thinking truncated to 80 chars — users cannot see full data
- No grouping by round — the causal chain (thinking → tool calls → results) is lost in noise
- Missing metadata: model name, token usage, tool success/failure status, per-tool timing
- The AgentProgressPanel (5-agent pipeline) is designed for Draft Agents but the workbench uses WriterOrchestrator — the panel is effectively dead UI

**Goal:** Redesign the log display as a structured, developer-friendly trace panel with round-based grouping, expandable details, and rich metadata.

## Scope

- **In scope:** WriterOrchestrator flow (orchestrator agent loop → writer streaming) log display
- **Out of scope:** Draft Agents pipeline (AgentProgressPanel stays as-is), overall page layout

## Data Structure

### Backend SSE Events (existing, with additions)

No new event types. Additions to existing events:

| Event | New Fields | Source |
|-------|-----------|--------|
| `tool_call` | `round` (int) | agent_loop round counter |
| `tool_result` | `round` (int), `full_result` (str), `status` ("ok"\|"error"), `tool_elapsed_ms` (int) | agent_loop |
| `thinking` | `round` (int) | agent_loop round counter |
| `orchestrator_status` | `model` (str) | LlmRouter client model name |
| `phase_summary` | `token_usage` ({prompt_tokens, completion_tokens, total_tokens}) | Accumulated from LLM responses |

### Frontend State

Replace flat `agentTimeline: ref([])` with structured state:

```typescript
interface AgentTraceState {
  orchestrator: {
    model: string;
    status: 'idle' | 'running' | 'done' | 'error';
    rounds: RoundGroup[];
    summary: {
      toolCount: number;
      roundCount: number;
      elapsedMs: number;
      tokenUsage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
    } | null;
  };
  writer: {
    model: string;
    status: 'idle' | 'running' | 'done' | 'error';
    wordCount: number;
    elapsedMs: number;
  };
}

interface RoundGroup {
  roundNum: number;
  thinking: string | null;       // Full content, never truncated
  toolCalls: ToolCallPair[];     // tool_call + tool_result paired
  promptSnapshot: {
    messages: object[];
    charCount: number;
  } | null;
  elapsedMs: number;
  status: 'running' | 'done';
}

interface ToolCallPair {
  name: string;
  display: string;               // Human-readable from TOOL_DISPLAY_FORMATTERS
  input: object;
  summary: string | null;        // Short summary (default display)
  fullResult: string | null;     // Complete result (expandable)
  status: 'pending' | 'done' | 'error';
  toolElapsedMs: number;
}
```

### Event → State Mapping

1. `prompt_snapshot` with `round=N` → create `rounds[N]` RoundGroup
2. `thinking` with `round=N` → set `rounds[N].thinking`
3. `tool_call` with `round=N` → push ToolCallPair (status=pending) to `rounds[N].toolCalls`
4. `tool_result` with `round=N`, `name=X` → find matching pending ToolCallPair by name, set result/status/timing
5. `phase_summary` → set `orchestrator.summary`
6. `orchestrator_status` with `phase=writing` → set `writer.status = 'running'`, capture `model`
7. `writer_token` → increment `writer.wordCount`

## UI Component

### Component: `AgentTracePanel.vue`

Single file component, replaces the timeline-log template block (WriterWorkbenchView.vue lines 400-427).

Props: `state: AgentTraceState`

Internal structure (all rendered within the single SFC, no separate component files):

```
AgentTracePanel
├── OrchestratorHeader         // "编排层 · model-name · status"
├── RoundCard × N              // One per round
│   ├── RoundHeader            // "Round N ── elapsed"
│   ├── ThinkingBlock          // 💭 collapsible, 2 lines default
│   ├── ToolCallList           // Tool call rows
│   │   └── ToolCallRow × N   // "↗ display  ✓  elapsed" + expandable result
│   └── PromptSnapshotToggle   // "📋 提示词快照 (N字)" deep-collapsed
├── PhaseSummaryBar            // "■ 收集完成 · N tools · N rounds · elapsed · tokens"
└── WriterSection              // "写作层 · model · status" + word count
```

### Render Details

**OrchestratorHeader:**
```
编排层 · gemini-2.5-pro · running ●
```
Model name from orchestrator_status event. Status dot: blue spinning (running), green (done), red (error).

**RoundCard:**
- Border: `1px solid var(--border-subtle)`, border-radius 8px
- Active round: left border accent highlight (blue, 3px)
- Completed rounds: slightly dimmed opacity (0.85)
- Header: `Round N` left, elapsed time right, monospace

**ThinkingBlock:**
- Icon: 💭
- Default: first 2 lines (~120 chars), with `[更多]` toggle
- Expanded: full content, pre-wrap, with `[收起]` toggle
- Color: muted/italic (same as current `.tl-thinking`)

**ToolCallRow:**
- Layout: `icon | display text | status badge | elapsed`
- Icon: ↗ (call), colored by status
- Status: `✓` green (ok), `✗` red (error), `●` blue spinning (pending)
- Clickable to expand result panel below
- Expanded result: monospace pre block with full_result, bordered, max-height 300px with scroll

**PromptSnapshotToggle:**
- Icon: 📋
- Default: collapsed, shows only `"提示词快照 (N 字)"`
- Expanded: same rendering as current (role header + pre content), max-height 400px scroll

**PhaseSummaryBar:**
- Single line, copper accent color, font-weight 600
- Format: `■ 收集完成 · N 次工具调用 · N 轮对话 · Xs · ~N tokens`

**WriterSection:**
- Header: `写作层 · model-name · status`
- During streaming: `✍ 正在写作... N 字` with pulsing icon
- After completion: `✍ 写作完成 · N 字 · Xs`

### Visual Style

Follow existing dark theme CSS variables:
- `--surface-primary`, `--border-subtle`, `--text-primary`, `--text-sub`
- `--accent-copper` for summaries
- Font: `var(--font-mono)` for the panel
- Expand/collapse: smooth CSS transition (`max-height` + opacity)
- Auto-scroll to bottom on new events (existing behavior, preserved)

## Backend Changes

### File: `backend/app/services/writer_agent/agent_loop.py`

1. **Add `round` field** to `tool_call`, `tool_result`, `thinking` events (pass `round_num` into `_stamp()` or merge inline)

2. **Add `full_result` to tool_result events** (~line 175-190):
   - Currently: `yield {"type": "tool_result", "name": ..., "summary": summary}`
   - Change to: also include `"full_result": result_str` (the raw result before truncation)
   - Add `"status": "ok"` or `"status": "error"` based on whether tool execution raised
   - Add `"tool_elapsed_ms"` — record `time.monotonic()` before/after each tool execution

3. **Extract token usage** from LLM response:
   - After `response = self.client.chat_with_tools(...)`, check `response.usage`
   - Accumulate into `self.total_usage` dict
   - Include per-round usage in prompt_snapshot or a new per-round event field

### File: `backend/app/services/writer_agent/orchestrator.py`

1. **Add `model` to orchestrator_status events** (~line 71, 188):
   - Get model name from `orchestrator_client.model` or similar
   - Include in: `yield {"type": "orchestrator_status", "model": model_name, ...}`

2. **Add `token_usage` to phase_summary** (~line 131-137):
   - Sum accumulated usage from agent_loop
   - Include: `"token_usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}`

### File: `backend/app/services/writer_agent/tools.py`

No changes. `TOOL_DISPLAY_FORMATTERS` already provides good human-readable descriptions.

## Frontend Changes

### File: `frontend/src/components/AgentTracePanel.vue` (NEW)

New single-file component implementing the full trace panel UI described above.

### File: `frontend/src/views/WriterWorkbenchView.vue`

1. **Replace data model**: `agentTimeline` ref → `agentTrace` reactive object (AgentTraceState)
2. **Replace event handler**: rewrite `onEvent()` to populate `agentTrace` instead of pushing to flat array
3. **Replace template**: swap timeline-log block (lines 400-427) with `<AgentTracePanel :state="agentTrace" />`
4. **Remove dead code**: `timelineBody()`, `timelineIcon()`, `promptSnapshotLabel()` helper functions
5. **Remove AgentProgressPanel usage** from writer orchestrator flow (it's only meaningful for Draft Agents)

### File: `frontend/src/views/WriterWorkbenchView.css`

Remove `.tl-*` and `.timeline-log` styles (lines 855-955). All styling moves into AgentTracePanel's scoped style.

## Verification

1. **Backend unit test**: Verify agent_loop yields events with `round`, `full_result`, `status`, `tool_elapsed_ms` fields
2. **Frontend manual test**: 
   - Run a write_scene task, verify rounds are grouped correctly
   - Click tool results to expand full content
   - Click thinking to expand full content  
   - Verify model name and token counts display
   - Verify prompt snapshots still expandable
   - Verify auto-scroll behavior preserved
3. **Build check**: `cd frontend && npm run build` passes without errors
