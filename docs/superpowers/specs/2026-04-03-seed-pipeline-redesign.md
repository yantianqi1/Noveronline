# Seed Pipeline Redesign: Sequential Reading + Character Agent Construction

## 1. Problem Statement

The current seed extraction pipeline has 14 sequential stages that produce poor-quality novel analysis results. Root causes:

1. **Blind extraction**: Stage 6 (`extract_local_facts`) extracts entities/events without any story context, producing fragmented, inaccurate results
2. **Redundant processing**: Stage 9 (`contextual_block_analysis`) re-does extraction with context, but its higher-quality output is mostly unused downstream
3. **Fragile regex**: Stage 3 (`skeleton_timeline`) uses rigid regex patterns (2-4 char Chinese names only, suffix-based org detection) that miss most entities
4. **Progressive information loss**: Each merge/compress/aggregate step discards information (2 evidence per entity, summary overwrites, tail-truncated story context)
5. **Coarse anchors**: World state snapshots see only 3-4% of actual text, track binary active/inactive states
6. **Conservative entity resolution**: Substring + edit-distance-1 matching misses most aliases

The final output (seed_analysis) contains only names, mention counts, and importance tiers, insufficient for downstream worldline simulation or character dialogue agents.

## 2. Design Goals

- **Two-phase separation**: Novel comprehension and character agent construction are independent phases
- **Sequential reading**: LLM reads the novel like a human, maintaining running context
- **Scale support**: From short stories (<100k chars) to million-character completed novels
- **Quality over speed**: Accept more LLM calls and longer processing time for deeper understanding
- **Agent-ready output**: Produce character profiles with personality, speech style, relationships, knowledge boundaries, and motivations

## 3. Architecture Overview

```
Current: 14 stages, regex-heavy, blind extraction
    → extract_text → segment_chapters → skeleton_timeline → build_blocks
    → anchor_generation → extract_local_facts → merge_story_memory
    → entity_resolution → contextual_block_analysis → chapter_card_generation
    → consistency_audit → build_continuity → seed_analysis → ontology

New: 4 stages, LLM-driven sequential reading
    Phase 1: Novel Comprehension
      → Stage 1: Text Extraction + Smart Segmentation
      → Stage 2: Sequential Deep Reading (core)
    Phase 2: Character Agent Construction
      → Stage 3: Global Integration + Ontology
      → Stage 4: Per-Character Agent Profile Generation
```

### Stages Removed and Why

| Removed Stage | Reason |
|--------------|--------|
| skeleton_timeline | LLM identifies entities naturally during reading |
| build_blocks | Replaced by smart segmentation (chapter-boundary-aware) |
| anchor_generation | Running reading notes serve as continuous anchors |
| extract_local_facts | Merged into sequential reading (no more blind extraction) |
| merge_story_memory | Reading notes ARE the memory, built incrementally |
| entity_resolution | LLM resolves aliases during reading |
| contextual_block_analysis | Eliminated redundancy; reading does analysis in one pass |
| consistency_audit | LLM flags inconsistencies during reading |
| build_continuity | Reading notes contain continuity |

### Stages Kept/Adapted

| Stage | Disposition |
|-------|------------|
| extract_text | Kept as-is (file parsing) |
| segment_chapters | Chapter detection regex kept; block building replaced by smart segmentation |
| seed_analysis | Replaced by global integration (richer output) |
| ontology | Kept but receives much higher quality input |

## 4. Stage 1: Text Extraction + Smart Segmentation

### 4.1 Text Extraction

Unchanged. `FileParser` extracts text from PDF/TXT/MD uploads.

### 4.2 Smart Segmentation (`SmartNovelSegmenter`)

**Purpose**: Group complete chapters into reading segments that fit within the LLM context window.

**Input**:
- Raw text from file extraction
- User-configured target token limit per segment (e.g., 50000)

**Process**:
1. Detect chapter boundaries using existing regex patterns from `NovelChapterSegmenter`
2. If no chapter markers found: split on blank lines / separator patterns to form pseudo-chapters
3. Estimate token count per chapter (Chinese: ~1.5 tokens/char, English: whitespace-based)
4. Greedy bin-packing: accumulate chapters into segments, finalize segment when adding next chapter would exceed token limit

**Rules**:
- Never split mid-chapter
- Single chapter exceeding limit becomes its own segment
- Token estimation is conservative (overestimate rather than underestimate)

**Output**:
```json
{
  "segment_count": 20,
  "segments": [
    {
      "segment_id": "seg_001",
      "chapters": [{"chapter_id": "ch_001", "title": "...", "content": "..."}],
      "chapter_range": "1-28",
      "estimated_tokens": 48500
    }
  ]
}
```

**Configuration**: Target token limit is user-configured in the upload form's advanced settings.

## 5. Stage 2: Sequential Deep Reading

### 5.1 Reading Notes Structure

The reading process maintains a `ReadingNotes` object with three tiers:

```
ReadingNotes:
  core_facts:                    # Tier 1: NEVER compressed
    characters: {}               # name → {aliases, status, identity, first_seen, personality_traits, speech_style, goals, key_quotes}
    organizations: {}            # name → {type, status, members_mentioned, purpose}
    world_rules: []              # Power systems, social rules, physical laws
    key_locations: {}            # name → {description, significance}

  relationship_graph: []         # Tier 2: Append-only
    # [{source, target, relation, trigger, evidence, segment_id}]

  plot_state:                    # Tier 3: Milestone-based (see 5.3)
    arc_summaries: []            # Permanent per-arc summaries (~800 chars each)
    volume_summaries: []         # Permanent per-volume summaries (for very long novels)
    recent_segment_summaries: [] # Last 2 segments' detailed summaries
    open_threads: []             # Currently unresolved plot threads
    narrative_phase: ""          # Current story phase
```

### 5.2 Per-Segment LLM Call

Each segment is processed with a single LLM call.

**Input (assembled into prompt)**:
- System prompt with analysis instructions
- Reading notes (serialized, respecting token budget)
- Current segment full text

**System Prompt** (core instructions, final version will be in Chinese):
```
你是一名专业的小说分析师，正在顺序精读一部小说。

你会收到：
1. 之前阅读的笔记（包含已识别的角色、关系、剧情进展）
2. 当前阅读段的完整正文

请以读者的视角分析当前段，输出以下 JSON：

{
  "segment_summary": "200-400 chars summarizing core plot of this segment",

  "character_updates": [
    {
      "name": "character name",
      "aliases": ["alias1", "title1"],
      "is_new": true/false,
      "status": "active/dead/injured/missing/unknown",
      "identity": "brief identity description",
      "personality_traits": ["trait1", "trait2"],
      "speech_style": "description of how they speak",
      "goals": "current motivation",
      "key_actions": ["key action in this segment"],
      "knowledge_gained": ["information learned in this segment"],
      "quote_examples": ["representative dialogue from text"]
    }
  ],

  "relationship_changes": [
    {
      "source": "character A",
      "target": "character B",
      "previous_state": "prior relationship",
      "new_state": "relationship after this segment",
      "trigger": "what caused the change",
      "evidence": "textual evidence"
    }
  ],

  "plot_threads": [
    {
      "thread": "thread description",
      "status": "opened/progressed/resolved",
      "detail": "progress details"
    }
  ],

  "world_building": [
    {"fact": "newly revealed world-building detail", "evidence": "textual evidence"}
  ],

  "consistency_notes": ["contradictions or notable points"],

  "narrative_phase": "setup/development/conflict/climax/turning_point/resolution"
}
```

### 5.3 Milestone-Based Memory (Preventing Information Loss)

**Problem**: Continuous compression of a single summary degrades information through repeated processing.

**Solution**: Hierarchical milestones, each created once and never modified.

#### Level 1: Segment Summaries
- Each segment's `segment_summary` (200-400 chars) is saved to disk
- Last 2 segments' summaries are kept in full detail in active context

#### Level 2: Arc Summaries
- Every N segments (default: 5), create an **arc summary** via one LLM call:
  - Input: the N segment summaries + core_facts context
  - Output: ~800 char integrated arc summary
  - **Written to disk and never modified**
- All arc summaries are included in subsequent reading contexts

#### Level 3: Volume Summaries (for very long novels only)
- When arc count exceeds threshold (default: 10 arcs), create volume summaries:
  - Every 10 arcs → one ~2000 char volume summary
  - **Written to disk and never modified**
- Active context then carries: all volume summaries + current volume's arc summaries

#### Adaptive Context Assembly

```python
if segment_count <= 10:      # Short novel: no arcs needed
    context = core_facts + all_segment_summaries + current_segment

elif segment_count <= 50:    # Medium novel: two levels
    context = core_facts + all_arc_summaries + recent_2_segment_detail + current_segment

else:                        # Long novel: three levels
    context = core_facts + all_volume_summaries + current_volume_arc_summaries
              + recent_2_segment_detail + current_segment
```

#### Information Compression Depth

| Approach | Max compression passes for early content |
|----------|------------------------------------------|
| Current pipeline (repeated compression) | 10-20 passes |
| New milestone approach | **Max 2 passes** (segment → arc → volume) |

### 5.4 Token Budget Allocation

For a 128k context model:

| Component | Token Budget | Notes |
|-----------|-------------|-------|
| System prompt | ~2k | Fixed |
| core_facts | ~10-15k | Grows slowly; tiered if >100 characters |
| relationship_graph | ~5-8k | Append-only; compressed if >200 entries |
| Arc/volume summaries | ~10-20k | All milestones, never compressed |
| Recent segment detail | ~3k | Last 2 segments |
| Current segment text | ~50k | User-configured target |
| Output space | ~10k | LLM response |
| **Total** | **~90-108k** | **Fits 128k context** |

### 5.5 Notes Update Protocol

After each segment reading:

1. **core_facts**: Merge `character_updates` and `world_building`
   - Characters: **accumulate** traits, quotes, actions (never overwrite)
   - New characters: add to registry
   - Status changes: update status, preserve previous status in history
   - When character count > 100: demote characters with fewest segment appearances to minimal entries (name + status only)

2. **relationship_graph**: Append all `relationship_changes` with segment_id

3. **plot_state**:
   - Add current segment summary to `recent_segment_summaries`
   - Update `open_threads` (add opened, mark resolved)
   - Update `narrative_phase`
   - Every N segments: trigger arc summary generation

4. **Persist to disk**: Save full reading notes after each segment (checkpoint for resume)

### 5.6 LLM Call Count Estimates

| Novel Size | Segments | Arc Summaries | Volume Summaries | Total Phase 1 |
|-----------|----------|---------------|-----------------|---------------|
| 100k chars (short) | ~3 | 0 | 0 | ~3 |
| 500k chars (medium) | ~10 | ~2 | 0 | ~12 |
| 1M chars (long) | ~20 | ~4 | 0 | ~24 |
| 3M chars (very long) | ~60 | ~12 | ~1 | ~73 |

## 6. Stage 3: Global Integration

After sequential reading completes, the reading notes contain a comprehensive understanding. This stage structures it for output.

### 6.1 Entity Archive (Rule-Based)
- Extract from `core_facts.characters` → character list with aliases, status, identity, personality traits
- Extract from `core_facts.organizations` → organization list
- Extract from `relationship_graph` → relationship network with evolution history
- Character importance determined by: segment appearance count + key action count + relationship density

### 6.2 Ontology Generation (1 LLM Call)
- Input: complete reading notes (much higher quality than current fragmented story_memory)
- Reuse existing `StoryOntologyGenerator` prompt structure
- Output: entity types, edge types, story focus dimensions

### 6.3 Seed Analysis Output (Rule-Based)
- Generate `seed_analysis.json` compatible with current frontend
- Enriched fields: importance based on multi-factor scoring, relationship evolution chains preserved, full character profiles

### 6.4 Artifact Persistence
All intermediate artifacts saved to project directory:
- `reading_notes.json` — final reading notes
- `segment_summaries/` — per-segment summaries
- `arc_summaries/` — per-arc summaries
- `volume_summaries/` — per-volume summaries (if applicable)
- `seed_analysis.json` — aggregated analysis
- `ontology` — stored in project record

## 7. Stage 4: Per-Character Agent Profile Generation

### 7.1 Purpose
Generate agent-ready profiles for each important character, supporting both worldline simulation and character dialogue.

### 7.2 Process
For each character with importance above threshold (configurable):

**One LLM call per character (fully concurrent)**:

Input:
- Global story summary (arc/volume summaries)
- Character's complete entry from core_facts
- Character's complete relationship history from relationship_graph
- Character's quote examples

Output schema:
```json
{
  "basic_info": {
    "name": "",
    "aliases": [],
    "identity": "",
    "status": "alive/dead/..."
  },

  "personality": {
    "core_traits": ["resolute", "suspicious"],
    "values": ["loyalty", "justice"],
    "fears": ["loss of control"],
    "decision_pattern": "description of decision-making style"
  },

  "speech": {
    "style": "concise and sharp, rarely uses metaphors",
    "verbal_habits": ["catchphrases"],
    "tone_range": "normally cold, becomes passionate when...",
    "example_quotes": ["quote1", "quote2"]
  },

  "relationships": [
    {
      "target": "character B",
      "current_state": "complex rivalry",
      "evolution": ["initial hostility", "forced cooperation", "grudging respect"],
      "attitude": "surface coldness masking acknowledgment"
    }
  ],

  "capabilities": {
    "skills": ["swordsmanship"],
    "limitations": ["poor social skills"],
    "resources": ["possesses artifact X"]
  },

  "knowledge_boundary": {
    "knows": ["truth about X"],
    "does_not_know": ["Y is a spy"],
    "believes_wrongly": ["thinks Z is dead"]
  },

  "motivation": {
    "ultimate_goal": "...",
    "current_objective": "...",
    "internal_conflict": "..."
  }
}
```

### 7.3 LLM Call Count
- Typically 10-30 important characters
- All calls are independent and fully concurrent
- Total: 10-30 concurrent calls

## 8. Progress Tracking

The existing `SeedTaskProgressTracker` is adapted for the new 4-stage pipeline.

### New Stage Definitions

| Stage Key | Label | Progress Range |
|-----------|-------|---------------|
| `extract_text` | Extracting text | 0-5% |
| `smart_segmentation` | Smart segmentation | 5-10% |
| `sequential_reading` | Sequential deep reading | 10-75% |
| `arc_summary` | Generating arc summaries | (within sequential_reading) |
| `global_integration` | Global integration | 75-85% |
| `ontology` | Ontology generation | 85-90% |
| `agent_profiles` | Character agent profiles | 90-100% |

### Per-Segment Progress
Within `sequential_reading`, progress is linear across segments:
- Segment 1/20 = 10% + (1/20) * 65% = 13.25%
- Segment 10/20 = 10% + (10/20) * 65% = 42.5%

## 9. Frontend Impact

### Upload Form Changes
- Add "Target token limit per segment" to advanced settings (default: 50000)
- Remove block-related configuration if any

### Pipeline Visualization
- Update `seedUploadTaskView.js` stage definitions to match new 4-stage pipeline
- Fewer stages but each stage represents more meaningful work

### Seed Analysis Display
- `SeedAnalysisPanel.vue` can show richer character data (personality, speech style)
- Relationship display can show evolution chains instead of single state

### New: Agent Profile Display
- New component to display generated agent profiles
- Preview character personality, speech examples, relationship map

## 10. Migration Strategy

### Backend
- New services: `SmartNovelSegmenter`, `SequentialReader`, `ReadingNotesManager`, `CharacterAgentProfileGenerator`
- Adapt: `SeedExtractRunner` (new pipeline), `SeedExtractTaskService` (new service wiring)
- Adapt: `SeedAnalysisAggregator` (read from reading notes instead of story_memory)
- Keep: `StoryOntologyGenerator` (better input), `FileParser`, chapter detection regex
- Remove: `SkeletonTimelineBuilder`, `AnalysisBlockBuilder`, `AnchorPointBuilder`, `LocalBlockFactExtractor`, `StoryMemoryBuilder`, `ContextualBlockAnalyzer`, `EntityResolutionService`, `ContinuityConsistencyAuditor`, `ChapterContinuityService`
- Keep but optional: `ChapterCardGenerator` (can derive from segment summaries if needed)

### Frontend
- Update `seedUploadTaskView.js` stage definitions
- Update `PipelineVisualization.vue` for new stages
- Adapt `SeedAnalysisPanel.vue` for richer data
- New component for agent profile display

### Data Compatibility
- New pipeline produces `seed_analysis.json` with backward-compatible fields plus enriched data
- Existing projects using old format continue to work (read path unchanged)
- New projects get enriched format

## 11. Verification

1. **Unit tests**: SmartNovelSegmenter (chapter boundary detection, bin-packing, edge cases)
2. **Unit tests**: ReadingNotesManager (merge protocol, milestone creation, budget enforcement)
3. **Integration test**: End-to-end pipeline with short test novel (offline mode for non-LLM stages)
4. **Quality comparison**: Run both old and new pipelines on same novel, compare character/relationship coverage
5. **Scale test**: Process 100k, 500k, 1M char novels, verify token budgets stay within limits
6. **Frontend**: Verify pipeline visualization, seed analysis display, agent profile display

## 12. File Inventory

### New Files
- `backend/app/services/smart_novel_segmenter.py`
- `backend/app/services/sequential_reader.py`
- `backend/app/services/reading_notes_manager.py`
- `backend/app/services/character_agent_profile_generator.py`
- `backend/app/services/sequential_reader_prompts.py`
- `backend/app/services/character_agent_prompts.py`

### Modified Files
- `backend/app/services/seed_extract_runner.py` — complete rewrite of pipeline
- `backend/app/services/seed_extract_task_service.py` — new service wiring
- `backend/app/services/seed_analysis_aggregator.py` — read from reading notes
- `backend/app/services/seed_task_progress.py` — new stage definitions
- `frontend/src/views/overview/seedUploadTaskView.js` — new stage definitions
- `frontend/src/views/overview/PipelineVisualization.vue` — adapt to fewer stages
- `frontend/src/views/overview/SeedUploadFormFields.vue` — add token limit config
- `frontend/src/views/overview/SeedAnalysisPanel.vue` — richer display

### Removed Files (or deprecated)
- `backend/app/services/skeleton_timeline_builder.py`
- `backend/app/services/analysis_block_builder.py`
- `backend/app/services/anchor_point_builder.py`
- `backend/app/services/local_block_fact_extractor.py`
- `backend/app/services/story_memory_builder.py`
- `backend/app/services/contextual_block_analyzer.py`
- `backend/app/services/entity_resolution_service.py`
- `backend/app/services/continuity_consistency_auditor.py`
- `backend/app/services/chapter_continuity_service.py`
- Related prompt files and support files
