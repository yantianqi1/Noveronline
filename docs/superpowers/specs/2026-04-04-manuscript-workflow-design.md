# Manuscript Workflow Design

## Context

The writer workbench currently generates prose via multi-agent pipeline (orchestrator → writer → post-processor) and stores results as `scenes` within `chapters`. However, the workflow lacks:

1. An explicit "save/commit" action for finalized prose
2. A full-novel manuscript viewer
3. A clear continuation workflow with plot continuity guarantees
4. Separation between AI-generated drafts (scenes) and author-finalized text (manuscript)

This design introduces a **manuscript layer** — an append-only sequence of committed text blocks that represents the author's finalized novel content, independent of the scene/chapter system used by the AI agents.

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Commit granularity | Free-form paragraph | Author may commit any selection of text, not bound to scene boundaries |
| Manuscript viewer | Slide-in drawer | Stay in writing context, no page navigation needed |
| Continuation UX | Hybrid mode | Show "continue next" button after commit; user decides when to proceed |
| Continuity mechanism | Visible summary + transparent tail text | User sees summary/threads; LLM receives raw tail text for style continuity |
| Architecture | Separate `manuscript_blocks` table | Clean separation from AI scene system; avoids polluting scene semantics |

---

## 1. Data Model

New table in existing `novel.sqlite3` (per-project):

```sql
CREATE TABLE manuscript_blocks (
    block_id              TEXT PRIMARY KEY,          -- mb_{nanoid}
    project_id            TEXT NOT NULL,
    block_order           INTEGER NOT NULL,          -- global sequence number (gap-spaced: 10, 20, 30...)
    content               TEXT NOT NULL,             -- committed prose text
    word_count            INTEGER DEFAULT 0,
    chapter_tag           TEXT,                      -- optional user-assigned chapter label (e.g. "第三章")
    source_scene_id       TEXT,                      -- optional: originating scene reference
    -- continuity context (LLM-extracted asynchronously on commit)
    summary               TEXT,                      -- auto-generated block summary
    open_threads_json     TEXT,                      -- unresolved plot threads (JSON array of strings)
    pov_entity_id         TEXT,                      -- POV character for this block
    involved_entities_json TEXT,                     -- characters present (JSON array of entity IDs)
    location              TEXT,                      -- scene location
    narrative_note        TEXT,                      -- narrative state (tone, pacing, tension level)
    committed_at          TEXT NOT NULL,             -- ISO timestamp
    UNIQUE(project_id, block_order)
);

CREATE INDEX idx_mb_project ON manuscript_blocks(project_id, block_order);

-- Full-text search
CREATE VIRTUAL TABLE manuscript_fts USING fts5(
    content,
    summary,
    content=manuscript_blocks,
    content_rowid=rowid
);

-- FTS sync triggers (INSERT/UPDATE/DELETE)
```

**Key properties:**
- `block_order` uses gap spacing (10, 20, 30...) to allow insertion between blocks without reordering all
- `chapter_tag` is optional — users can assign chapter labels post-hoc via batch tagging
- `source_scene_id` traces back to the AI-generated scene that produced this content
- Continuity fields (`summary`, `open_threads_json`, `pov_entity_id`, `involved_entities_json`, `location`, `narrative_note`) are populated asynchronously by LLM after commit — null until extraction completes

---

## 2. Commit Workflow

### Flow

```
User clicks [Commit to Manuscript]
    │
    ├─ Option A: Commit all workspace content
    └─ Option B: Commit selected text only
         │
         ▼
    Position selection (default: append to end)
         │
         ▼
    POST /api/writer-agent/manuscript/<project_id>/commit
    {
      "content": "...",
      "source_scene_id": "sc_xxx" (optional),
      "insert_after_block_id": null (null = append)
    }
         │
         ▼
    Backend:
      1. Create manuscript_block with next block_order
      2. Compute word_count
      3. Return block immediately
      4. Spawn background thread for LLM metadata extraction
         │
         ▼
    Frontend:
      1. Show "Committed" toast notification
      2. Show [Continue Next Paragraph] button
      3. Workspace retains current content (not auto-cleared)
```

### Async Metadata Extraction

On commit, a background thread calls LLM to extract:
- `summary`: 1-2 sentence summary of the block
- `open_threads_json`: unresolved plot threads introduced or continued
- `pov_entity_id`: POV character (matched against project entities)
- `involved_entities_json`: characters present in this block
- `location`: where the scene takes place
- `narrative_note`: tone/pacing/tension description

If LLM is unavailable, commit still succeeds — metadata fields remain null and can be retried later.

### Metadata Extraction Prompt

The LLM receives the block content plus the previous block's summary (if available) and extracts a structured JSON:

```
Given this novel passage and its preceding context, extract:
1. summary: 1-2 sentence summary of what happens in this passage
2. open_threads: list of unresolved plot threads (new or continuing)
3. pov_entity: the point-of-view character name
4. involved_entities: list of all character/entity names present
5. location: where this scene takes place
6. narrative_note: tone, pacing, tension level (1 sentence)

Respond in JSON format matching the field names above.
```

Entity names from extraction are matched against the project's entity table to resolve IDs. Unmatched names are stored as-is in a text field.

---

## 3. Continuation Mechanism

### Frontend: Continuation Context Panel

When user clicks [Continue Next Paragraph]:

1. Workspace clears
2. Top of workspace shows **Continuation Context Panel**:

```
┌──────────────────────────────────────────┐
│ 📌 Recent Summary                         │
│ Block 12 · Li Ming discovers the tunnel   │
│ Block 13 · Wang Xue stalls the guards     │
│                                           │
│ 💡 Active Threads                          │
│ • Mysterious letter sender unrevealed     │
│ • Underground palace guards alerted?      │
│                                           │
│ 📍 Current: Underground entrance · POV: LM│
└──────────────────────────────────────────┘
```

Data source: `GET /api/writer-agent/manuscript/<project_id>/continuation-context`

### Backend: Token-Budget Context Loading

Instead of a fixed block count, use a **token budget** (default 8000 tokens) to load context:

```
Budget allocation (~8000 tokens):
├── Last block full tail text         ~2000 tokens
├── Blocks N-1 to N-K summaries       ~3000 tokens (dynamic)
├── Aggregated open_threads            ~1000 tokens
├── POV / location / narrative_note    ~500 tokens
└── Reserved for entity/relationship   ~1500 tokens
```

Loading algorithm:
1. Load last block's `content` tail (last 800-1200 chars)
2. Walk backwards through blocks, adding `summary` until budget exhausted
3. Aggregate `open_threads_json` from loaded blocks, deduplicate
4. Include last block's `pov_entity_id`, `location`, `narrative_note`

### Backend: Agent Tool Integration

The orchestrator agent continues its full think → tool_call → result loop. Three new tools are added:

| Tool | Purpose |
|------|---------|
| `get_manuscript_context` | Returns recent block summaries + tail text + threads, auto-trimmed to token budget |
| `search_manuscript` | FTS5 full-text search across committed manuscript blocks |
| `get_manuscript_stats` | Total word count, block count, chapter tag list |

During `task_type = "continue"`, the orchestrator:
1. Calls `get_manuscript_context` for recent continuity data
2. Calls `query_entity` / `query_relationship` as needed for character depth
3. Optionally calls `search_manuscript` to recall earlier plot points
4. Builds `writing_brief` with `continuation_context` section:

```json
{
  "continuation_context": {
    "recent_summaries": ["Block 12 summary...", "Block 13 summary..."],
    "active_threads": ["thread1", "thread2"],
    "last_pov": "entity_id",
    "last_location": "Underground entrance",
    "narrative_note": "Tense, accelerating pace",
    "tail_text": "...last 800 chars of raw prose..."
  }
}
```

The writer agent's system prompt includes continuation instructions to match style/rhythm/voice with `tail_text`.

---

## 4. Manuscript Drawer (Viewer)

A slide-in drawer from the right side of the writer workbench.

### Trigger
- [View Manuscript] button in the writer workbench toolbar
- Drawer slides in from right, width: `min(680px, 60vw)`
- Background: writer workbench dims to opacity 0.3, non-interactive

### Layout

```
┌─────────────────────────────────────┐
│ 📖 Manuscript Viewer        [×Close]│
│                                     │
│ Total: 12,450 words · 15 blocks     │
│ ┌─ Chapter Jump ─────────────────┐  │
│ │ Ch.1(3) Ch.2(5) Ch.3(4) ...   │  │
│ └────────────────────────────────┘  │
│                                     │
│ ── Chapter 1 ──────────────────     │
│ [Block 1] Prose content here...     │
│                    [Edit] [Delete]  │
│                                     │
│ [Block 2] More prose content...     │
│                    [Edit] [Delete]  │
│                                     │
│ ── Chapter 2 ──────────────────     │
│ [Block 3] Even more prose...        │
│                    [Edit] [Delete]  │
│ ...                                 │
│                                     │
│ ┌────────────────────────────────┐  │
│ │ [Drag Reorder] [Batch Tag]    │  │
│ │ [Export Full Text]            │  │
│ └────────────────────────────────┘  │
└─────────────────────────────────────┘
```

### Features

| Feature | Description |
|---------|-------------|
| Browse | Display all committed blocks ordered by block_order, grouped by chapter_tag |
| Chapter jump | Tab bar for quick navigation to chapter positions |
| Inline edit | Click [Edit] to modify block content in-place, save updates the block |
| Delete block | Click [Delete] with confirmation, subsequent blocks auto-reorder |
| Drag reorder | Drag blocks to rearrange order |
| Batch chapter tag | Select multiple blocks, assign chapter_tag in bulk |
| Export | Concatenate all block content by order, download as TXT or MD |
| Word count | Header shows total words and block count |

---

## 5. API Design

### Manuscript Management

```
POST   /api/writer-agent/manuscript/<project_id>/commit
       Body: { content, source_scene_id?, insert_after_block_id? }
       Returns: { block_id, block_order, word_count, committed_at }

GET    /api/writer-agent/manuscript/<project_id>
       Query: ?include_content=true (default true)
       Returns: { blocks: [...], total_words, total_blocks }

PUT    /api/writer-agent/manuscript/block/<block_id>
       Body: { content?, chapter_tag? }
       Returns: { block_id, word_count, updated fields }

DELETE /api/writer-agent/manuscript/block/<block_id>
       Returns: { ok: true }

PUT    /api/writer-agent/manuscript/<project_id>/reorder
       Body: { block_ids: ["mb_1", "mb_3", "mb_2"] }
       Returns: { ok: true }

PUT    /api/writer-agent/manuscript/<project_id>/tag
       Body: { block_ids: [...], chapter_tag: "第三章" }
       Returns: { ok: true, updated_count }

GET    /api/writer-agent/manuscript/<project_id>/export
       Query: ?format=txt|md
       Returns: plain text file download

GET    /api/writer-agent/manuscript/<project_id>/continuation-context
       Query: ?token_budget=8000
       Returns: { recent_summaries, active_threads, last_pov, last_location, narrative_note, tail_text }
```

---

## 6. File Change Summary

### Backend — New Files

| File | Purpose |
|------|---------|
| `services/writer_agent/manuscript_service.py` | Manuscript CRUD: commit, list, edit, delete, reorder, tag, export |
| `services/writer_agent/manuscript_context_builder.py` | Continuation context assembly with token-budget loading |

### Backend — Modified Files

| File | Change |
|------|--------|
| `services/writer_agent/novel_db.py` | Add `manuscript_blocks` table schema + CRUD methods + FTS5 index |
| `api/writer_agent.py` | Add manuscript route group (8 endpoints) |
| `services/writer_agent/tools.py` | Add 3 new tool definitions: `get_manuscript_context`, `search_manuscript`, `get_manuscript_stats` |
| `services/writer_agent/tool_executors.py` | Add 3 new tool executor implementations |
| `services/writer_agent/orchestrator.py` | Inject continuation_context into writing_brief for `continue` task_type |
| `services/writer_agent/prompts.py` | Add continuation-specific prompt with coherence instructions |

### Frontend — New Files

| File | Purpose |
|------|---------|
| `views/writer/ManuscriptDrawer.vue` | Full manuscript viewer drawer component |
| `views/writer/ContinuationContextPanel.vue` | Summary + threads + POV display panel |

### Frontend — Modified Files

| File | Change |
|------|--------|
| `views/WriterWorkbenchView.vue` | Add [Commit] button, [View Manuscript] button, [Continue Next] button, integrate continuation panel |
| `views/writer/SceneEditor.vue` | Add [Commit Selection] button on text selection toolbar |
| `api/writerAgent.js` | Add manuscript API client functions |

---

## 7. Verification Plan

### Unit Tests

1. `test_manuscript_service.py`:
   - Commit block, verify persistence and block_order assignment
   - Insert between existing blocks, verify order gap handling
   - Edit block content, verify word_count update
   - Delete block, verify removal
   - Reorder blocks, verify new order
   - Batch tag blocks, verify chapter_tag update
   - Export full text, verify concatenation order

2. `test_manuscript_context_builder.py`:
   - Token budget loading with various block counts
   - Summary aggregation and deduplication of open_threads
   - Edge case: no blocks committed yet
   - Edge case: blocks with null metadata (LLM extraction pending)

3. `test_manuscript_tools.py`:
   - `get_manuscript_context` tool returns correctly formatted context
   - `search_manuscript` FTS5 search returns relevant blocks
   - `get_manuscript_stats` returns accurate counts

### Integration Tests

1. Full commit → continuation workflow:
   - Commit a block via API
   - Verify async metadata extraction completes
   - Request continuation-context, verify summary/threads populated
   - Run writer agent with `task_type=continue`, verify it receives manuscript context

### Manual Verification

1. Write/generate prose in workbench → click [Commit] → verify block appears in manuscript drawer
2. Select partial text → click [Commit Selection] → verify only selected text committed
3. Click [Continue Next] → verify continuation panel shows summary/threads → generate next passage → verify coherence
4. In manuscript drawer: edit a block, delete a block, reorder blocks, batch tag, export
5. Verify async metadata: commit a block, wait a few seconds, reopen drawer → summary/threads should be populated
