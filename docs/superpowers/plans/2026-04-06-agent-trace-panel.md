# Agent Trace Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat monospace timeline log in the writer workbench with a structured, round-grouped trace panel that shows full expandable details, tool status, model names, token usage, and per-tool timing.

**Architecture:** Backend SSE events gain metadata fields (round, full_result, status, model, token_usage). Frontend replaces flat `agentTimeline` array with structured `agentTrace` reactive state grouped by round. A new `AgentTracePanel.vue` component renders round cards with expandable thinking/tool results/prompt snapshots.

**Tech Stack:** Python/Flask (backend), Vue 3 + Naive UI (frontend), existing CSS variable dark theme.

**Spec:** `docs/superpowers/specs/2026-04-06-agent-trace-panel-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/utils/llm_client.py` | Return usage from `chat_with_tools` |
| Modify | `backend/app/services/writer_agent/agent_loop.py` | Add round/status/timing/usage to events |
| Modify | `backend/app/services/writer_agent/orchestrator.py` | Add model name, token_usage to phase events |
| Modify | `backend/tests/test_writer_agent.py` | Update tests for new event fields |
| Create | `frontend/src/components/AgentTracePanel.vue` | New structured trace panel component |
| Modify | `frontend/src/views/WriterWorkbenchView.vue` | Wire new component, replace flat timeline |
| Modify | `frontend/src/views/WriterWorkbenchView.css` | Remove old `.tl-*` styles |

---

### Task 1: Backend — Return usage from `chat_with_tools`

**Files:**
- Modify: `backend/app/utils/llm_client.py:121-149`
- Modify: `backend/app/services/writer_agent/agent_loop.py:94-100`
- Modify: `backend/tests/test_writer_agent.py:487-499`

The `chat_with_tools` method currently returns `response.choices[0].message`, discarding usage. We need usage accessible to `AgentLoop`. The cleanest approach: attach usage to the returned message object as an attribute, avoiding a breaking API change.

- [ ] **Step 1: Write test for usage passthrough**

Add to `backend/tests/test_writer_agent.py`, inside `TestAgentLoop`:

```python
def test_loop_events_include_round_and_usage(self):
    from app.services.writer_agent.agent_loop import AgentLoop
    from app.services.writer_agent.tools import NOVEL_TOOLS

    mock_client = MockLLMClient([
        MockMessage(
            content=None,
            tool_calls=[MockToolCall("query_entity", {"name": "林远"})],
        ),
        MockMessage(
            content='{"task": "write_scene"}',
            tool_calls=None,
        ),
    ])

    loop = AgentLoop(mock_client, NOVEL_TOOLS, "你是编排助手", self.TEST_PROJECT)
    events = list(loop.run("写第一章"))

    # tool_call and tool_result should carry round number
    tool_call_evt = next(e for e in events if e["type"] == "tool_call")
    assert tool_call_evt["round"] == 0

    tool_result_evt = next(e for e in events if e["type"] == "tool_result")
    assert tool_result_evt["round"] == 0
    assert "status" in tool_result_evt
    assert "tool_elapsed_ms" in tool_result_evt
    assert "full_result" in tool_result_evt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestAgentLoop::test_loop_events_include_round_and_usage -v`

Expected: FAIL — `round` key missing from tool_call event.

- [ ] **Step 3: Modify `llm_client.py` to attach usage to returned message**

In `backend/app/utils/llm_client.py`, change `chat_with_tools` (line 143-147):

```python
            response = self._chat_with_retry(kwargs, call_id)
            usage = self._extract_usage(response)
            if step_ctx:
                self._record_trace(step_ctx, None, response.choices[0].message.content or "", None, t0, "chat_with_tools", usage=usage)
            msg = response.choices[0].message
            msg._usage = usage  # Attach for caller access
            return msg
```

- [ ] **Step 4: Modify `agent_loop.py` to add round, status, timing, usage to events**

In `backend/app/services/writer_agent/agent_loop.py`:

4a. Add instance variable for accumulated usage. In `__init__` (after line 46):

```python
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
```

4b. After LLM response (after line 100, inside the round loop), accumulate usage:

```python
            # Accumulate token usage
            usage = getattr(response, "_usage", None)
            if usage:
                for k in self.total_usage:
                    self.total_usage[k] += usage.get(k, 0)
```

4c. Add `round` to thinking event (line 128):

```python
                yield {"type": "thinking", **self._stamp(), "round": round_num, "content": response.content.strip()}
```

4d. Add `round` to tool_call event (line 142):

```python
                yield {"type": "tool_call", **self._stamp(), "round": round_num, "name": tool_name, "input": tool_input, "display": display}
```

4e. Rewrite the tool_result yield block (lines 172-181) to add round, status, per-tool timing:

```python
            # Append results in original order (deterministic message history)
            for tc, tool_name, tool_input in pending:
                _, resolved_name, result = results_map[tc.id]
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                summary = result[:200] + "..." if len(result) > 200 else result
                yield {
                    "type": "tool_result",
                    **self._stamp(),
                    "round": round_num,
                    "name": resolved_name,
                    "summary": summary,
                    "full_result": result,
                    "status": "ok",
                    "tool_elapsed_ms": int((time.monotonic() - self.t0) * 1000) - self._stamp()["elapsed_ms"],
                }
```

Wait — that timing approach is wrong. We need per-tool timing. The tool execution happens inside `_run_tool`. Let's wrap tool execution with timing instead.

Replace the `_run_tool` function (lines 146-149) and the result map logic:

```python
            def _run_tool(item):
                tc, tool_name, tool_input = item
                t_start = time.monotonic()
                try:
                    result = execute_tool(tool_name, tool_input, self.project_id)
                    elapsed = int((time.monotonic() - t_start) * 1000)
                    return tc, tool_name, result, "ok", elapsed
                except Exception as exc:
                    elapsed = int((time.monotonic() - t_start) * 1000)
                    return tc, tool_name, f"工具执行失败: {exc}", "error", elapsed

            read_pending = [p for p in pending if p[1] not in _WRITE_TOOL_NAMES]
            write_pending = [p for p in pending if p[1] in _WRITE_TOOL_NAMES]

            results_map: Dict[str, tuple] = {}

            # Phase A: read tools in parallel
            if len(read_pending) == 1:
                tc, tool_name, result, status, tool_ms = _run_tool(read_pending[0])
                results_map[tc.id] = (tc, tool_name, result, status, tool_ms)
            elif read_pending:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    futures = {pool.submit(_run_tool, item): item[0].id for item in read_pending}
                    for future in concurrent.futures.as_completed(futures):
                        tc, tool_name, result, status, tool_ms = future.result()
                        results_map[tc.id] = (tc, tool_name, result, status, tool_ms)

            # Phase B: write tools serially (SQLite WAL safety)
            for item in write_pending:
                tc, tool_name, result, status, tool_ms = _run_tool(item)
                results_map[tc.id] = (tc, tool_name, result, status, tool_ms)

            # Append results in original order (deterministic message history)
            for tc, tool_name, tool_input in pending:
                _, resolved_name, result, status, tool_ms = results_map[tc.id]
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                summary = result[:200] + "..." if len(result) > 200 else result
                yield {
                    "type": "tool_result",
                    **self._stamp(),
                    "round": round_num,
                    "name": resolved_name,
                    "summary": summary,
                    "full_result": result,
                    "status": status,
                    "tool_elapsed_ms": tool_ms,
                }
```

4f. Add `round` to prompt_snapshot event (line 87-93) — already has `"round": round_num`, no change needed.

- [ ] **Step 5: Update MockLLMClient to support _usage attribute**

In `backend/tests/test_writer_agent.py`, update `MockLLMClient.chat_with_tools`:

```python
    def chat_with_tools(self, messages, tools, temperature=0.3, max_tokens=4096):
        if self.call_count >= len(self.responses):
            msg = MockMessage(content="No more responses", tool_calls=None)
            msg._usage = None
            return msg
        response = self.responses[self.call_count]
        self.call_count += 1
        response._usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        return response
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestAgentLoop -v`

Expected: All TestAgentLoop tests PASS, including the new one.

- [ ] **Step 7: Verify existing tests still pass**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py -v`

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/utils/llm_client.py backend/app/services/writer_agent/agent_loop.py backend/tests/test_writer_agent.py
git commit -m "feat: add round/status/timing/usage metadata to agent loop events"
```

---

### Task 2: Backend — Add model name and token_usage to orchestrator events

**Files:**
- Modify: `backend/app/services/writer_agent/orchestrator.py:70-71,87-89,130-137,187-188`

- [ ] **Step 1: Add model name to orchestrator_status events**

In `backend/app/services/writer_agent/orchestrator.py`, after `orchestrator_client = self.router.build_client("writer_orchestrator")` (line 89), capture the model name:

```python
        orchestrator_model = orchestrator_client.model
```

Then update the first orchestrator_status event (line 71):

```python
        yield {"type": "orchestrator_status", "phase": "starting", **_stamp(), "message": "编排层启动中...", "model": orchestrator_model}
```

And the writing phase status event (line 188). First capture the writer model. After `composer = WriterComposer(llm_router=self.router)` (line 193), extract the writer model name. Read the WriterComposer to find how it gets the client:

The writer model name should come from `self.router.build_client("writer_composer")`. Add:

```python
        try:
            writer_model = self.router.build_client("writer_composer").model
        except Exception:
            writer_model = "unknown"
```

Then update the writing phase status:

```python
        yield {"type": "orchestrator_status", "phase": "writing", **_stamp(), "message": "写作层启动中...", "model": writer_model}
```

- [ ] **Step 2: Add token_usage to phase_summary**

After the agent loop finishes (line 130-137), the agent_loop object has `total_usage`. Pass it through:

```python
        yield {
            "type": "phase_summary",
            **_stamp(),
            "phase": "collecting",
            "tool_count": tool_count,
            "message": f"收集完成：{tool_count}次工具调用，耗时{_stamp()['elapsed_ms'] / 1000:.1f}s",
            "token_usage": agent_loop.total_usage,
        }
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/writer_agent/orchestrator.py
git commit -m "feat: add model name and token_usage to orchestrator SSE events"
```

---

### Task 3: Frontend — Create `AgentTracePanel.vue` component

**Files:**
- Create: `frontend/src/components/AgentTracePanel.vue`

This is the core new component. It receives a reactive `state` prop (AgentTraceState) and renders the round-grouped card layout.

- [ ] **Step 1: Create the component file**

Create `frontend/src/components/AgentTracePanel.vue` with the full implementation:

```vue
<template>
  <div class="agent-trace-panel">
    <!-- Orchestrator Section -->
    <div v-if="state.orchestrator.status !== 'idle'" class="trace-section">
      <div class="trace-section-header">
        <span class="trace-section-title">编排层</span>
        <span v-if="state.orchestrator.model" class="trace-model-badge">{{ state.orchestrator.model }}</span>
        <span class="trace-status-dot" :class="state.orchestrator.status"></span>
      </div>

      <!-- Round Cards -->
      <div
        v-for="round in state.orchestrator.rounds"
        :key="round.roundNum"
        class="round-card"
        :class="{ active: round.status === 'running' }"
      >
        <div class="round-header">
          <span class="round-label">Round {{ round.roundNum + 1 }}</span>
          <span v-if="round.elapsedMs" class="round-elapsed">{{ (round.elapsedMs / 1000).toFixed(1) }}s</span>
        </div>

        <!-- Thinking Block -->
        <div v-if="round.thinking" class="thinking-block">
          <span class="thinking-icon">💭</span>
          <div class="thinking-content">
            <template v-if="!round._thinkingExpanded">
              <span class="thinking-preview">{{ truncate(round.thinking, 120) }}</span>
              <button v-if="round.thinking.length > 120" class="expand-btn" @click="round._thinkingExpanded = true">[更多]</button>
            </template>
            <template v-else>
              <pre class="thinking-full">{{ round.thinking }}</pre>
              <button class="expand-btn" @click="round._thinkingExpanded = false">[收起]</button>
            </template>
          </div>
        </div>

        <!-- Tool Calls -->
        <div v-if="round.toolCalls.length" class="tool-call-group">
          <div
            v-for="(tc, idx) in round.toolCalls"
            :key="idx"
            class="tool-call-item"
          >
            <div class="tool-call-row" @click="tc._expanded = !tc._expanded">
              <span class="tool-call-icon">↗</span>
              <span class="tool-call-display">{{ tc.display || tc.name }}</span>
              <span class="tool-call-status" :class="tc.status">
                <template v-if="tc.status === 'done'">✓</template>
                <template v-else-if="tc.status === 'error'">✗</template>
                <template v-else><span class="tool-spinner"></span></template>
              </span>
              <span v-if="tc.toolElapsedMs" class="tool-elapsed">{{ (tc.toolElapsedMs / 1000).toFixed(1) }}s</span>
              <span v-if="tc.fullResult" class="expand-indicator">{{ tc._expanded ? '▼' : '▶' }}</span>
            </div>
            <!-- Expanded Result -->
            <div v-if="tc._expanded && tc.fullResult" class="tool-result-panel">
              <pre class="tool-result-content">{{ tc.fullResult }}</pre>
            </div>
          </div>
        </div>

        <!-- Prompt Snapshot -->
        <div v-if="round.promptSnapshot" class="prompt-snapshot-toggle">
          <div class="prompt-snapshot-header" @click="round._promptExpanded = !round._promptExpanded">
            <span class="prompt-snapshot-icon">📋</span>
            <span class="prompt-snapshot-label">提示词快照 ({{ round.promptSnapshot.charCount.toLocaleString() }} 字)</span>
            <span class="expand-indicator">{{ round._promptExpanded ? '▼' : '▶' }}</span>
          </div>
          <div v-if="round._promptExpanded" class="prompt-snapshot-detail">
            <div
              v-for="(msg, mIdx) in round.promptSnapshot.messages"
              :key="mIdx"
              class="prompt-msg"
            >
              <div class="prompt-role">{{ msg.role }}</div>
              <pre class="prompt-content">{{ msg.content }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Phase Summary Bar -->
      <div v-if="state.orchestrator.summary" class="phase-summary-bar">
        <span class="phase-summary-icon">■</span>
        <span class="phase-summary-text">
          收集完成 · {{ state.orchestrator.summary.toolCount }} 次工具调用
          · {{ state.orchestrator.summary.roundCount }} 轮对话
          · {{ (state.orchestrator.summary.elapsedMs / 1000).toFixed(1) }}s
          <template v-if="state.orchestrator.summary.tokenUsage?.total_tokens">
            · ~{{ state.orchestrator.summary.tokenUsage.total_tokens.toLocaleString() }} tokens
          </template>
        </span>
      </div>
    </div>

    <!-- Writer Section -->
    <div v-if="state.writer.status !== 'idle'" class="trace-section writer-section">
      <div class="trace-section-header">
        <span class="trace-section-title">写作层</span>
        <span v-if="state.writer.model" class="trace-model-badge">{{ state.writer.model }}</span>
        <span class="trace-status-dot" :class="state.writer.status"></span>
      </div>
      <div class="writer-progress">
        <span class="writer-icon" :class="{ streaming: state.writer.status === 'running' }">✍</span>
        <span v-if="state.writer.status === 'running'">正在写作... {{ state.writer.wordCount.toLocaleString() }} 字</span>
        <span v-else-if="state.writer.status === 'done'">
          写作完成 · {{ state.writer.wordCount.toLocaleString() }} 字
          <template v-if="state.writer.elapsedMs"> · {{ (state.writer.elapsedMs / 1000).toFixed(1) }}s</template>
        </span>
        <span v-else-if="state.writer.status === 'error'">写作失败</span>
      </div>
    </div>

    <!-- Error -->
    <div v-if="state.error" class="trace-error">
      <span class="trace-error-icon">✗</span>
      <span class="trace-error-msg">{{ state.error }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  state: {
    type: Object,
    required: true,
  },
});

function truncate(text, maxLen) {
  if (!text || text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
}
</script>

<style scoped>
.agent-trace-panel {
  font-family: var(--font-mono, "SF Mono", "Fira Code", monospace);
  font-size: 12px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Section ── */
.trace-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trace-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.trace-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
}
.trace-model-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(110, 168, 254, 0.15);
  color: #6ea8fe;
  font-weight: 500;
}
.trace-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.trace-status-dot.running {
  background: #6ea8fe;
  animation: dot-pulse 1.5s ease-in-out infinite;
}
.trace-status-dot.done { background: #75b798; }
.trace-status-dot.error { background: #ea868f; }
.trace-status-dot.idle { background: #555; }

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ── Round Card ── */
.round-card {
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--surface-primary, #12121e);
  transition: border-color 0.2s;
}
.round-card.active {
  border-left: 3px solid #6ea8fe;
}
.round-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.round-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-sub, #888);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.round-elapsed {
  font-size: 11px;
  color: var(--text-sub, #888);
}

/* ── Thinking ── */
.thinking-block {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.thinking-icon {
  flex-shrink: 0;
  margin-top: 1px;
}
.thinking-content {
  flex: 1;
  min-width: 0;
}
.thinking-preview {
  color: #999;
  font-style: italic;
}
.thinking-full {
  color: #999;
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: inherit;
  font-size: inherit;
}
.expand-btn {
  background: none;
  border: none;
  color: #6ea8fe;
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  font-family: inherit;
}
.expand-btn:hover { text-decoration: underline; }

/* ── Tool Calls ── */
.tool-call-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tool-call-item {
  display: flex;
  flex-direction: column;
}
.tool-call-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.tool-call-row:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.04));
}
.tool-call-icon {
  flex-shrink: 0;
  color: #6ea8fe;
  width: 14px;
  text-align: center;
}
.tool-call-display {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary, #e0e0e0);
}
.tool-call-status {
  flex-shrink: 0;
  font-size: 12px;
  width: 16px;
  text-align: center;
}
.tool-call-status.done { color: #75b798; }
.tool-call-status.error { color: #ea868f; }
.tool-call-status.pending { color: #6ea8fe; }
.tool-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(110, 168, 254, 0.3);
  border-top-color: #6ea8fe;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.tool-elapsed {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-sub, #888);
  width: 36px;
  text-align: right;
}
.expand-indicator {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-sub, #888);
  width: 12px;
  text-align: center;
}
.tool-result-panel {
  margin: 4px 0 4px 20px;
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
  max-height: 300px;
  overflow-y: auto;
}
.tool-result-content {
  padding: 8px 12px;
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-primary, #e0e0e0);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: inherit;
}

/* ── Prompt Snapshot ── */
.prompt-snapshot-toggle {
  margin-top: 2px;
}
.prompt-snapshot-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.prompt-snapshot-header:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.04));
}
.prompt-snapshot-icon { flex-shrink: 0; }
.prompt-snapshot-label {
  color: #c09060;
  font-weight: 500;
  font-size: 11px;
}
.prompt-snapshot-detail {
  margin: 4px 0 0 20px;
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 6px;
  background: var(--surface-primary, #12121e);
  max-height: 400px;
  overflow-y: auto;
}
.prompt-msg {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle, #2d2d44);
}
.prompt-msg:last-child { border-bottom: none; }
.prompt-role {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #6ea8fe;
  margin-bottom: 4px;
  letter-spacing: 0.5px;
}
.prompt-content {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary, #e0e0e0);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: inherit;
}

/* ── Phase Summary ── */
.phase-summary-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(184, 115, 51, 0.08);
  border: 1px solid rgba(184, 115, 51, 0.2);
}
.phase-summary-icon {
  color: var(--accent-copper, #b87333);
}
.phase-summary-text {
  color: var(--accent-copper, #b87333);
  font-weight: 600;
  font-size: 12px;
}

/* ── Writer Section ── */
.writer-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  color: var(--text-primary, #e0e0e0);
}
.writer-icon {
  font-size: 14px;
}
.writer-icon.streaming {
  animation: dot-pulse 1.5s ease-in-out infinite;
}

/* ── Error ── */
.trace-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(234, 134, 143, 0.1);
  border: 1px solid rgba(234, 134, 143, 0.3);
}
.trace-error-icon { color: #ea868f; font-weight: bold; }
.trace-error-msg { color: #ea868f; }
</style>
```

- [ ] **Step 2: Verify file created correctly**

Run: `ls -la frontend/src/components/AgentTracePanel.vue`

Expected: File exists.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AgentTracePanel.vue
git commit -m "feat: create AgentTracePanel component with round-grouped card layout"
```

---

### Task 4: Frontend — Wire `AgentTracePanel` into `WriterWorkbenchView`

**Files:**
- Modify: `frontend/src/views/WriterWorkbenchView.vue`
- Modify: `frontend/src/views/WriterWorkbenchView.css`

This task replaces the flat `agentTimeline` data model and event handlers with the structured `agentTrace` state, swaps the template, and removes dead code.

- [ ] **Step 1: Add import and replace data model**

In `frontend/src/views/WriterWorkbenchView.vue`:

1a. Add import (near line 504, after AgentProgressPanel import):

```javascript
import AgentTracePanel from "../components/AgentTracePanel.vue";
```

1b. Replace the flat timeline refs (around lines 591-596). Keep `agentTimeline` for now (other code may reference it), but add the new state. After `const agentSceneContent = ref("");` add:

```javascript
const agentTrace = reactive({
  orchestrator: {
    model: "",
    status: "idle",
    rounds: [],
    summary: null,
  },
  writer: {
    model: "",
    status: "idle",
    wordCount: 0,
    elapsedMs: 0,
  },
  error: "",
});

function resetAgentTrace() {
  agentTrace.orchestrator = { model: "", status: "idle", rounds: [], summary: null };
  agentTrace.writer = { model: "", status: "idle", wordCount: 0, elapsedMs: 0 };
  agentTrace.error = "";
}

function ensureRound(roundNum) {
  while (agentTrace.orchestrator.rounds.length <= roundNum) {
    agentTrace.orchestrator.rounds.push({
      roundNum: agentTrace.orchestrator.rounds.length,
      thinking: null,
      toolCalls: [],
      promptSnapshot: null,
      elapsedMs: 0,
      status: "running",
      _thinkingExpanded: false,
      _promptExpanded: false,
    });
  }
  return agentTrace.orchestrator.rounds[roundNum];
}
```

Add `reactive` to the Vue import at the top of the script section (it likely already imports `ref`, `computed`, etc.):

```javascript
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
```

1c. In `startGeneration()` and `handleWorldUpdate()` reset functions (around lines 750-758 and 1110-1114), add `resetAgentTrace()`:

Where `agentTimeline.value = []` appears, add `resetAgentTrace()` after it.

- [ ] **Step 2: Rewrite the `onEvent` handler**

Replace the entire onEvent handler inside `startGeneration()` (lines 1153-1243) with the new structured logic:

```javascript
      onEvent(event) {
        if (event.type === "orchestrator_status") {
          agentTrace.orchestrator.status = "running";
          if (event.model) {
            if (event.phase === "writing") {
              agentTrace.writer.model = event.model;
              agentTrace.writer.status = "running";
            } else {
              agentTrace.orchestrator.model = event.model;
            }
          }
          draftPhase.value = event.phase === "writing" ? "writing" : "collecting";
          message.value = event.message || "编排中...";
        } else if (event.type === "thinking") {
          const round = ensureRound(event.round ?? agentTrace.orchestrator.rounds.length - 1);
          round.thinking = event.content;
        } else if (event.type === "tool_call") {
          const round = ensureRound(event.round ?? agentTrace.orchestrator.rounds.length - 1);
          round.toolCalls.push({
            name: event.name,
            display: event.display || event.name,
            input: event.input,
            summary: null,
            fullResult: null,
            status: "pending",
            toolElapsedMs: 0,
            _expanded: false,
          });
        } else if (event.type === "tool_result") {
          const round = ensureRound(event.round ?? agentTrace.orchestrator.rounds.length - 1);
          const tc = round.toolCalls.find(
            (t) => t.name === event.name && t.status === "pending"
          );
          if (tc) {
            tc.summary = event.summary;
            tc.fullResult = event.full_result || event.summary;
            tc.status = event.status === "error" ? "error" : "done";
            tc.toolElapsedMs = event.tool_elapsed_ms || 0;
          }
        } else if (event.type === "prompt_snapshot") {
          const roundNum = event.round ?? 0;
          const round = ensureRound(roundNum);
          const charCount = (event.messages || []).reduce(
            (sum, m) => sum + (m.content?.length || 0), 0
          );
          round.promptSnapshot = { messages: event.messages, charCount };
          round.elapsedMs = event.elapsed_ms || 0;
        } else if (event.type === "phase_summary") {
          // Mark all orchestrator rounds as done
          agentTrace.orchestrator.rounds.forEach((r) => { r.status = "done"; });
          agentTrace.orchestrator.status = "done";
          agentTrace.orchestrator.summary = {
            toolCount: event.tool_count || 0,
            roundCount: agentTrace.orchestrator.rounds.length,
            elapsedMs: event.elapsed_ms || 0,
            tokenUsage: event.token_usage || null,
          };
        } else if (event.type === "writer_token") {
          draftPhase.value = "writing";
          agentTrace.writer.status = "running";
          agentSceneContent.value += (event.token || "");
          agentTrace.writer.wordCount = agentSceneContent.value.length;
        } else if (event.type === "outline_ready") {
          draftPhase.value = "done";
          outlineData.value = event.outline;
        } else if (event.type === "error") {
          error.value = event.message || "生成失败";
          agentStreaming.value = false;
          draftPhase.value = agentSceneContent.value ? "done" : "idle";
          agentTrace.error = event.message || "生成失败";
        }
      },
```

Update the `onDone` handler to set writer status:

```javascript
      onDone(event) {
        agentStreaming.value = false;
        draftPhase.value = "done";
        agentTrace.writer.status = "done";
        agentTrace.writer.elapsedMs = event.elapsed_ms || 0;
        if (event.outline_saved) {
          message.value = `大纲已保存：${event.scene_count} 个场景`;
          return;
        }
        const wc = event.word_count || agentSceneContent.value.length;
        message.value = `创作完成：${wc} 字`;
        agentTrace.writer.wordCount = wc;
        commitTargetChapterId.value = chapterId.value || "";
        loadScenes();
      },
```

- [ ] **Step 3: Replace template**

Replace the timeline-log template block (lines 399-427) with:

```html
          <div v-if="agentTrace.orchestrator.status === 'idle' && !agentTrace.error" class="review-hint">生成正文后，这里会显示 Agent 的实时工作流程。</div>
          <AgentTracePanel v-else :state="agentTrace" ref="traceScrollRef" />
```

Update the auto-scroll watch. Replace the `agentTimeline.value.length` watcher (lines 1312-1317) with:

```javascript
watch(
  () => agentTrace.orchestrator.rounds.length + agentTrace.writer.wordCount,
  () => {
    nextTick(() => {
      const el = traceScrollRef.value?.$el || traceScrollRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  },
);
```

Add `const traceScrollRef = ref(null);` near the other refs. Remove `const timelineScrollRef = ref(null);` if no longer referenced.

- [ ] **Step 4: Remove dead code**

Remove from `WriterWorkbenchView.vue`:
- `const AGENT_DEFS` array (lines 552-558) — no longer used by writer orchestrator flow
- `initAgentPhases()` function and its calls
- `updateAgentStatus()` function
- `agentPhases` ref
- `timelineBody()`, `timelineIcon()`, `promptSnapshotLabel()` functions (lines 1274-1310)
- `const _tlIcons` object (lines 1275-1278)
- The `AgentProgressPanel` import and template usage for the writer orchestrator flow (lines 314-320)

**Important:** Check if `agentPhases` is used in the `handleWorldUpdate` flow as well. If so, keep the relevant parts. Search for all references before removing.

- [ ] **Step 5: Remove old timeline CSS**

In `frontend/src/views/WriterWorkbenchView.css`, remove lines 855-955 (all `.timeline-log`, `.tl-*` styles). These are now in `AgentTracePanel.vue`'s scoped styles.

- [ ] **Step 6: Build check**

Run: `cd frontend && npm run build`

Expected: Build succeeds with no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/WriterWorkbenchView.vue frontend/src/views/WriterWorkbenchView.css frontend/src/components/AgentTracePanel.vue
git commit -m "feat: wire AgentTracePanel into writer workbench, replace flat timeline"
```

---

### Task 5: Handle world-update flow and cleanup

**Files:**
- Modify: `frontend/src/views/WriterWorkbenchView.vue`

The `handleWorldUpdate()` function also uses `agentTimeline` for its own SSE events. It needs to use `agentTrace` too.

- [ ] **Step 1: Find and update handleWorldUpdate**

Search for `handleWorldUpdate` in WriterWorkbenchView.vue. Its `onEvent` handler likely pushes to `agentTimeline`. Update it to populate `agentTrace` using the same pattern as `startGeneration`'s handler (from Task 4 Step 2).

Specifically: the world-update flow runs the same WriterOrchestrator agent loop, so the SSE events are identical. Reuse the same handler by extracting the onEvent/onDone logic into a shared function:

```javascript
function handleTraceEvent(event) {
  // ... the onEvent body from Task 4 Step 2
}

function handleTraceDone(event) {
  // ... the onDone body from Task 4 Step 2
}
```

Then use these in both `startGeneration` and `handleWorldUpdate`:

```javascript
await runWriterAgent(payload, {
  onEvent: handleTraceEvent,
  onDone: handleTraceDone,
  onError(event) { /* ... */ },
}, signal);
```

- [ ] **Step 2: Remove remaining agentTimeline references**

Search for any remaining `agentTimeline` references. Remove the ref declaration, any remaining pushes, and the old length watcher. If nothing else uses it, delete it entirely.

- [ ] **Step 3: Build check**

Run: `cd frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Run backend tests**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py -v`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/WriterWorkbenchView.vue
git commit -m "refactor: extract shared trace event handlers, remove agentTimeline"
```

---

### Task 6: Final verification

- [ ] **Step 1: Full backend test suite**

Run: `cd backend && PYTHONPATH=$(pwd) pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`

Expected: Build succeeds with no errors or warnings related to removed code.

- [ ] **Step 3: Manual smoke test (if server available)**

Start backend and frontend:
```bash
cd backend && FLASK_PORT=3888 uv run python run.py &
cd frontend && npm run dev -- --port 3999 &
```

Open writer workbench, run a write_scene task. Verify:
- Rounds are grouped into cards
- Thinking block shows with [更多] expand
- Tool calls show with ✓/✗ status and timing
- Tool results expand on click with full content
- Prompt snapshots expand on click
- Phase summary shows tool count, rounds, time, tokens
- Writer section shows model and word count
- Auto-scroll works during streaming
