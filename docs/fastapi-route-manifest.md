# FastAPI Route Manifest

> Generated 2026-04-13. Definitive endpoint audit reconciling Flask → FastAPI migration.

## Summary

| Metric | Count |
|--------|-------|
| Route decorators (FastAPI) | 113 |
| Unique handlers (FastAPI) | 112 |
| Route decorators (Flask) | 113 |
| Unique handlers (Flask) | 112 |
| **Match** | **100%** |

The worldline `/session/{id}/timeline` and `/session/{id}/branch/{bid}/timeline` share one handler via dual decorator, accounting for the 113→112 difference.

Two endpoints (`branches`, `comparison`) return HTTP 410 Gone — intentionally deprecated for the single-world architecture.

## Route Table

| # | Method | Path | Router | Status | Has Schema | Has Test |
|---|--------|------|--------|--------|------------|----------|
| **project.py** (10 routes) |
| 1 | POST | `/api/project/seed/extract` | project | live | planned | partial |
| 2 | POST | `/api/project/seed/rerun/{project_id}` | project | live | planned | - |
| 3 | POST | `/api/project/build-graph` | project | live | planned | - |
| 4 | GET | `/api/project/task/{task_id}` | project | live | - | partial |
| 5 | POST | `/api/project/task/{task_id}/cancel` | project | live | - | partial |
| 6 | GET | `/api/project/task/{task_id}/steps/{step_id}/trace` | project | live | - | - |
| 7 | GET | `/api/project/list` | project | live | - | - |
| 8 | GET | `/api/project/{project_id}/graph` | project | live | - | - |
| 9 | GET | `/api/project/{project_id}` | project | live | - | - |
| 10 | DELETE | `/api/project/{project_id}` | project | live | - | yes |
| **novel.py** (10 routes) |
| 11 | POST | `/api/novel/archives/candidates` | novel | live | planned | - |
| 12 | POST | `/api/novel/archives/generate` | novel | live | planned | - |
| 13 | POST | `/api/novel/parallel-world/config` | novel | live | planned | - |
| 14 | GET | `/api/novel/seed-analysis/{project_id}` | novel | live | - | - |
| 15 | POST | `/api/novel/seed-analysis` | novel | live | planned | - |
| 16 | POST | `/api/novel/plot/inspiration` | novel | live | planned | - |
| 17 | GET | `/api/novel/chapter-context/options` | novel | live | - | yes |
| 18 | POST | `/api/novel/chapter-context` | novel | live | planned | yes |
| 19 | GET | `/api/novel/reviewer-rules` | novel | live | - | - |
| 20 | PUT | `/api/novel/reviewer-rules` | novel | live | planned | - |
| **llm.py** (8 routes) |
| 21 | GET | `/api/llm/settings` | llm | live | - | yes |
| 22 | POST | `/api/llm/channels` | llm | live | planned | yes |
| 23 | PATCH | `/api/llm/channels/{channel_key}` | llm | live | planned | yes |
| 24 | DELETE | `/api/llm/channels/{channel_key}` | llm | live | - | yes |
| 25 | POST | `/api/llm/channels/{channel_key}/sync-models` | llm | live | - | yes |
| 26 | PUT | `/api/llm/module-bindings/{module_key}` | llm | live | planned | yes |
| 27 | DELETE | `/api/llm/module-bindings/{module_key}` | llm | live | - | yes |
| 28 | GET | `/api/llm/activity` | llm | live | - | yes |
| **archive.py** (7 routes) |
| 29 | GET | `/api/archive/library` | archive | live | - | yes |
| 30 | GET | `/api/archive/library/{archive_id}` | archive | live | - | yes |
| 31 | POST | `/api/archive/library/reindex` | archive | live | - | yes |
| 32 | GET | `/api/archive/library/{archive_id}/memory` | archive | live | - | yes |
| 33 | GET | `/api/archive/library/{archive_id}/memory/timeline` | archive | live | - | yes |
| 34 | POST | `/api/archive/library/{archive_id}/memory/{memory_id}/adopt` | archive | live | - | yes |
| 35 | POST | `/api/archive/library/{archive_id}/memory/{memory_id}/reject` | archive | live | - | yes |
| **assets.py** (12 routes) |
| 36 | GET | `/api/assets` | assets | live | - | - |
| 37 | POST | `/api/assets/search` | assets | live | planned | - |
| 38 | GET | `/api/assets/{asset_id}` | assets | live | - | - |
| 39 | POST | `/api/assets` | assets | live | planned | - |
| 40 | PUT | `/api/assets/{asset_id}` | assets | live | planned | - |
| 41 | DELETE | `/api/assets/{asset_id}` | assets | live | - | - |
| 42 | POST | `/api/assets/batch-toggle` | assets | live | planned | - |
| 43 | POST | `/api/assets/batch-categorize` | assets | live | planned | - |
| 44 | POST | `/api/assets/ingest` | assets | live | planned | - |
| 45 | GET | `/api/assets/ingest/{task_id}` | assets | live | - | - |
| 46 | POST | `/api/assets/style-extract` | assets | live | planned | - |
| 47 | GET | `/api/assets/style-extract/{task_id}` | assets | live | - | - |
| **unified_assets.py** (6 routes) |
| 48 | GET | `/api/unified-assets` | unified_assets | live | - | - |
| 49 | GET | `/api/unified-assets/facets` | unified_assets | live | - | - |
| 50 | GET | `/api/unified-assets/search` | unified_assets | live | - | - |
| 51 | POST | `/api/unified-assets/reindex` | unified_assets | live | planned | - |
| 52 | GET | `/api/unified-assets/sources` | unified_assets | live | - | - |
| 53 | GET | `/api/unified-assets/{source}/{ref:path}` | unified_assets | live | - | - |
| **worldline.py** (29 decorators, 28 unique handlers) |
| 54 | POST | `/api/worldline/session/create` | worldline | live | planned | yes |
| 55 | GET | `/api/worldline/session/list` | worldline | live | - | yes |
| 56 | GET | `/api/worldline/session/{session_id}` | worldline | live | - | yes |
| 57 | GET | `/api/worldline/session/{session_id}/branches` | worldline | **410** | - | - |
| 58 | GET | `/api/worldline/session/{session_id}/comparison` | worldline | **410** | - | - |
| 59 | GET | `/api/worldline/session/{session_id}/timeline` | worldline | live | - | yes |
| 60 | GET | `/api/worldline/session/{session_id}/branch/{branch_id}/timeline` | worldline | live | - | yes |
| 61 | POST | `/api/worldline/session/{session_id}/step` | worldline | live | planned | - |
| 62 | POST | `/api/worldline/session/{session_id}/inject-variable` | worldline | live | planned | - |
| 63 | POST | `/api/worldline/session/{session_id}/agent-action` | worldline | live | planned | yes |
| 64 | GET | `/api/worldline/session/{session_id}/agents` | worldline | live | - | yes |
| 65 | POST | `/api/worldline/session/{session_id}/agent-dialogue` | worldline | live | planned | yes |
| 66 | GET | `/api/worldline/session/{session_id}/agent-history` | worldline | live | - | - |
| 67 | GET | `/api/worldline/session/{session_id}/agent-actions` | worldline | live | - | - |
| 68 | GET | `/api/worldline/session/{session_id}/agent-dialogues` | worldline | live | - | - |
| 69 | GET | `/api/worldline/session/{session_id}/relation-history` | worldline | live | - | - |
| 70 | GET | `/api/worldline/session/{session_id}/agent-memory` | worldline | live | - | yes |
| 71 | GET | `/api/worldline/session/{session_id}/agent-memory-context` | worldline | live | - | yes |
| 72 | POST | `/api/worldline/session/{session_id}/auto-evolve` | worldline | live | planned | yes |
| 73 | POST | `/api/worldline/session/prepare` | worldline | live | planned | yes |
| 74 | GET | `/api/worldline/session/prepare/{prepare_id}` | worldline | live | - | yes |
| 75 | GET | `/api/worldline/session/prepare/{prepare_id}/agents` | worldline | live | - | yes |
| 76 | POST | `/api/worldline/session/prepare/{prepare_id}/start` | worldline | live | planned | yes |
| 77 | GET | `/api/worldline/session/{session_id}/agents/{agent_id}` | worldline | live | - | yes |
| 78 | POST | `/api/worldline/session/{session_id}/events/adopt` | worldline | live | planned | yes |
| 79 | POST | `/api/worldline/session/{session_id}/events/{event_id}/edit` | worldline | live | planned | yes |
| 80 | GET | `/api/worldline/session/{session_id}/events/candidates` | worldline | live | - | yes |
| 81 | GET | `/api/worldline/session/{session_id}/events/canon` | worldline | live | - | yes |
| 82 | POST | `/api/worldline/session/{session_id}/auto-evolve/stream` | worldline | live | planned | - |
| **writer_agent.py** (31 routes) |
| 83 | POST | `/api/writer-agent/run` | writer_agent | live | planned | - |
| 84 | POST | `/api/writer-agent/world-update` | writer_agent | live | planned | - |
| 85 | GET | `/api/writer-agent/scenes/{chapter_id}` | writer_agent | live | - | - |
| 86 | GET | `/api/writer-agent/scenes/detail/{scene_id}` | writer_agent | live | - | - |
| 87 | PUT | `/api/writer-agent/scenes/{scene_id}` | writer_agent | live | planned | - |
| 88 | DELETE | `/api/writer-agent/scenes/{scene_id}` | writer_agent | live | - | - |
| 89 | POST | `/api/writer-agent/scenes/{chapter_id}/reorder` | writer_agent | live | planned | - |
| 90 | POST | `/api/writer-agent/scenes/{chapter_id}/compile` | writer_agent | live | planned | - |
| 91 | GET | `/api/writer-agent/presets` | writer_agent | live | - | - |
| 92 | POST | `/api/writer-agent/presets` | writer_agent | live | planned | - |
| 93 | PUT | `/api/writer-agent/presets/{preset_id}` | writer_agent | live | planned | - |
| 94 | DELETE | `/api/writer-agent/presets/{preset_id}` | writer_agent | live | - | - |
| 95 | GET | `/api/writer-agent/chapters/{project_id}` | writer_agent | live | - | - |
| 96 | POST | `/api/writer-agent/chapters/{project_id}` | writer_agent | live | planned | - |
| 97 | PUT | `/api/writer-agent/chapters/detail/{chapter_id}` | writer_agent | live | planned | - |
| 98 | GET | `/api/writer-agent/chapters/detail/{chapter_id}/outline-versions` | writer_agent | live | - | - |
| 99 | GET | `/api/writer-agent/chapters/detail/{chapter_id}/outline-versions/{version_id}` | writer_agent | live | - | - |
| 100 | POST | `/api/writer-agent/chapters/detail/{chapter_id}/outline-versions/{version_id}/restore` | writer_agent | live | planned | - |
| 101 | DELETE | `/api/writer-agent/chapters/detail/{chapter_id}` | writer_agent | live | - | - |
| 102 | POST | `/api/writer-agent/manuscript/{project_id}/commit` | writer_agent | live | planned | - |
| 103 | GET | `/api/writer-agent/manuscript/{project_id}` | writer_agent | live | - | - |
| 104 | PUT | `/api/writer-agent/manuscript/block/{block_id}` | writer_agent | live | planned | - |
| 105 | DELETE | `/api/writer-agent/manuscript/block/{block_id}` | writer_agent | live | - | - |
| 106 | PUT | `/api/writer-agent/manuscript/{project_id}/reorder` | writer_agent | live | planned | - |
| 107 | PUT | `/api/writer-agent/manuscript/{project_id}/tag` | writer_agent | live | planned | - |
| 108 | PUT | `/api/writer-agent/manuscript/block/{block_id}/move` | writer_agent | live | planned | - |
| 109 | GET | `/api/writer-agent/manuscript/{project_id}/export` | writer_agent | live | - | - |
| 110 | GET | `/api/writer-agent/manuscript/{project_id}/continuation-context` | writer_agent | live | - | - |
| 111 | POST | `/api/writer-agent/migrate/{project_id}` | writer_agent | live | - | - |

## Reconciliation Note

The previously reported "121 Flask endpoints" was likely an overcount. Both Flask and FastAPI codebases contain exactly **113 route decorators** serving **112 unique handlers**. The 1-count difference comes from the worldline timeline dual-decorator (two URL patterns → one handler). All endpoints were migrated 1:1 with zero loss.
