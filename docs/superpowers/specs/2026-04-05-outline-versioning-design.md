# Outline Versioning Design

## Summary

Add version history to chapter outlines. Each time the user manually saves an outline, the previous version is snapshotted. Users can browse history and restore any past version.

## Data Layer

### New Table: `outline_versions`

Added to `novel_db.py` schema alongside existing chapter tables.

```sql
CREATE TABLE IF NOT EXISTS outline_versions (
    version_id   TEXT PRIMARY KEY,        -- ov_{uuid12}
    chapter_id   TEXT NOT NULL REFERENCES chapter_content ON DELETE CASCADE,
    outline_json TEXT NOT NULL,            -- snapshot, same format as chapter_meta.outline_json
    label        TEXT DEFAULT '',          -- optional user annotation
    created_at   TEXT NOT NULL
)
CREATE INDEX IF NOT EXISTS idx_outline_versions_chapter
    ON outline_versions(chapter_id, created_at DESC)
```

### Save Flow (on user manual save)

1. Read current `chapter_meta.outline_json` for the chapter
2. Insert it into `outline_versions` with a new `version_id` and timestamp
3. Update `chapter_meta.outline_json` with the new value
4. If the chapter now has > 20 versions, delete the oldest

### Restore Flow

1. Read the target version's `outline_json` from `outline_versions`
2. Snapshot the current `chapter_meta.outline_json` into `outline_versions` (so restore is reversible)
3. Overwrite `chapter_meta.outline_json` with the target version's data

### Version Sources

Only user manual saves (clicking "save outline") create versions. Agent-generated outlines written directly by the orchestrator do NOT create versions.

### `chapter_meta.outline_json` Unchanged

Remains the single source of truth for the current outline. All existing read paths are unaffected.

## API Layer

Two new endpoints on `writer_agent_bp`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/chapters/detail/<chapter_id>/outline-versions?project_id=xxx` | List versions (version_id, label, created_at). Ordered by created_at DESC. Does NOT include outline_json body. |
| POST | `/chapters/detail/<chapter_id>/outline-versions/<version_id>/restore` | Restore a version. Request body: `{ "project_id": "..." }`. Snapshots current value before overwriting. |

### Existing Endpoint Changes

`PUT /chapters/detail/<chapter_id>` — no interface change. When `outline_json` is present in the payload, the backend internally snapshots the old value before updating.

### Frontend API Functions

In `writerAgent.js`:

```js
getOutlineVersions(chapterId, projectId)
restoreOutlineVersion(chapterId, versionId, projectId)
```

## UI Layer

### OutlineView.vue Changes

**Header additions:**
- "历史版本" toggle button in `outline-header`, next to the save button
- Small text input next to save button for optional version label (placeholder: "版本标注（可选）")

**Version history panel:**
- Collapsible panel below the header, shown when "历史版本" is active
- Each entry shows: sequence number, label (or "自动快照" if empty), created_at timestamp
- Clicking an entry enters **preview mode**

**Preview mode:**
- Outline becomes read-only, displaying the selected historical version
- Two buttons appear: "回退到此版本" and "取消预览"
- "回退到此版本" calls `restoreOutlineVersion`, then reloads current outline data
- "取消预览" returns to the current editable outline

### WriterWorkbenchView.vue Changes

- `handleOutlineSave` passes the optional `label` to the backend (new field in `updateChapter` payload, whitelisted in the API endpoint)
- After a successful restore, refresh the outline data for the active view mode

## Constraints

- Max 20 versions per chapter. Oldest deleted on overflow.
- No diff/comparison view. History is view-and-restore only.
- Version list endpoint returns metadata only (no outline_json body) to keep responses lightweight.

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/services/writer_agent/novel_db.py` | Add `outline_versions` table to schema, add `save_outline_version`, `list_outline_versions`, `restore_outline_version`, `get_outline_version` methods |
| `backend/app/services/writer_agent/chapter_service.py` | Wire version logic into `update_chapter`, add `list_outline_versions` and `restore_outline_version` methods |
| `backend/app/api/writer_agent.py` | Add two new endpoints, whitelist `label` field in update_chapter |
| `frontend/src/api/writerAgent.js` | Add `getOutlineVersions`, `restoreOutlineVersion` functions |
| `frontend/src/views/writer/OutlineView.vue` | Add version history panel, preview mode, label input |
| `frontend/src/views/WriterWorkbenchView.vue` | Pass label to save handler, handle restore refresh |
