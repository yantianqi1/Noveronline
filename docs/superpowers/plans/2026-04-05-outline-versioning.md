# Outline Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add version history to chapter outlines so users can browse and restore past versions.

**Architecture:** New `outline_versions` SQLite table stores snapshots. Each manual save snapshots the old value before overwriting. Two new API endpoints (list versions, restore version). OutlineView gains a collapsible history panel with preview/restore.

**Tech Stack:** Python/Flask/SQLite (backend), Vue 3 (frontend), pytest (tests)

---

### Task 1: Database — Add `outline_versions` table and DB methods

**Files:**
- Modify: `backend/app/services/writer_agent/novel_db.py`
- Test: `backend/tests/test_writer_agent.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_writer_agent.py`, add a new test class after the existing `TestNovelDB` class:

```python
class TestOutlineVersions:
    """Test outline version history in NovelDB."""

    TEST_PROJECT = f"__test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        yield
        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_outline_versions_table_exists(self):
        with self.db.connect(self.TEST_PROJECT) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "outline_versions" in tables

    def test_save_outline_version(self):
        vid = self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]')
        assert vid.startswith("ov_")
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 1
        assert versions[0]["version_id"] == vid
        assert "outline_json" not in versions[0]  # list should not include body

    def test_save_outline_version_with_label(self):
        vid = self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]', label="初版")
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert versions[0]["label"] == "初版"

    def test_get_outline_version(self):
        vid = self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]')
        version = self.db.get_outline_version(self.TEST_PROJECT, vid)
        assert version is not None
        assert version["outline_json"] == '[{"scene_order":1}]'

    def test_list_versions_ordered_desc(self):
        import time
        self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[]', label="v1")
        time.sleep(0.01)
        self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]', label="v2")
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 2
        assert versions[0]["label"] == "v2"  # newest first
        assert versions[1]["label"] == "v1"

    def test_max_20_versions(self):
        for i in range(22):
            self.db.save_outline_version(self.TEST_PROJECT, "ch_1", f'[{{"n":{i}}}]')
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 20

    def test_cascade_delete(self):
        self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[]')
        assert len(self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")) == 1
        self.db.delete_chapter(self.TEST_PROJECT, "ch_1")
        # After chapter deletion, versions should be gone (cascade)
        with self.db.connect(self.TEST_PROJECT) as conn:
            count = conn.execute("SELECT COUNT(*) FROM outline_versions").fetchone()[0]
        assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersions -v`
Expected: FAIL — `outline_versions` table does not exist, `save_outline_version` method not found.

- [ ] **Step 3: Add the table to schema**

In `backend/app/services/writer_agent/novel_db.py`, add the table at the end of `TABLE_STATEMENTS` (before the closing `)` at line 330):

```python
    """,
    """
    CREATE TABLE IF NOT EXISTS outline_versions (
        version_id   TEXT PRIMARY KEY,
        chapter_id   TEXT NOT NULL REFERENCES chapter_content ON DELETE CASCADE,
        outline_json TEXT NOT NULL,
        label        TEXT DEFAULT '',
        created_at   TEXT NOT NULL
    )
    """,
)
```

Add the index at the end of `INDEX_STATEMENTS` (before the closing `)` at line 703):

```python
    "CREATE INDEX IF NOT EXISTS idx_outline_versions_chapter ON outline_versions(chapter_id, created_at DESC)",
)
```

- [ ] **Step 4: Add DB methods**

In `backend/app/services/writer_agent/novel_db.py`, add the following methods to the `NovelDB` class, after the `update_chapter` method (after line 1062):

```python
    # -- outline versions ---------------------------------------------------

    def save_outline_version(
        self, project_id: str, chapter_id: str, outline_json: str, label: str = "",
    ) -> str:
        """Snapshot an outline into the version history. Returns version_id."""
        self.ensure_schema(project_id)
        version_id = f"ov_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.connect(project_id) as conn:
            conn.execute(
                """
                INSERT INTO outline_versions (version_id, chapter_id, outline_json, label, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (version_id, chapter_id, outline_json, label, now),
            )
            # Enforce max 20 versions per chapter
            conn.execute(
                """
                DELETE FROM outline_versions
                WHERE version_id IN (
                    SELECT version_id FROM outline_versions
                    WHERE chapter_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET 20
                )
                """,
                (chapter_id,),
            )
            conn.commit()
        return version_id

    def list_outline_versions(self, project_id: str, chapter_id: str) -> list[dict[str, Any]]:
        """List version metadata (without outline_json body) for a chapter."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT version_id, chapter_id, label, created_at
                FROM outline_versions
                WHERE chapter_id = ?
                ORDER BY created_at DESC
                """,
                (chapter_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def get_outline_version(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        """Get a single version including its outline_json."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            row = conn.execute(
                "SELECT * FROM outline_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            return _row_to_dict(row)
```

Ensure `import uuid` is present at the top of `novel_db.py`. (Check — it's already imported if used elsewhere; if not, add it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersions -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Update table existence test**

In `test_schema_creates_tables` within `TestNovelDB`, add `"outline_versions"` to the `expected` set.

- [ ] **Step 7: Run full test suite for TestNovelDB**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestNovelDB -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/writer_agent/novel_db.py backend/tests/test_writer_agent.py
git commit -m "feat: outline_versions table and NovelDB methods"
```

---

### Task 2: Service Layer — Wire versioning into ChapterService

**Files:**
- Modify: `backend/app/services/writer_agent/chapter_service.py`
- Test: `backend/tests/test_writer_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `TestOutlineVersions` in `backend/tests/test_writer_agent.py`:

```python
    def test_chapter_service_update_creates_version(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        # Set initial outline
        self.db.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"scene_order":1}]')
        # Update via service — should snapshot old value
        svc.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"scene_order":1},{"scene_order":2}]')
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 1
        full = self.db.get_outline_version(self.TEST_PROJECT, versions[0]["version_id"])
        assert full["outline_json"] == '[{"scene_order":1}]'  # old value snapshotted

    def test_chapter_service_update_passes_label(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        self.db.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[]')
        svc.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"x":1}]', outline_label="手动标注")
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert versions[0]["label"] == "手动标注"

    def test_chapter_service_update_no_version_without_outline(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        svc.update_chapter(self.TEST_PROJECT, "ch_1", title="改标题")
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 0  # no version created when outline not changed

    def test_chapter_service_restore(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        self.db.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"v":"old"}]')
        vid = self.db.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"v":"old"}]')
        self.db.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"v":"new"}]')
        svc.restore_outline_version(self.TEST_PROJECT, "ch_1", vid)
        ch = self.db.get_chapter(self.TEST_PROJECT, 1)
        assert ch["outline_json"] == '[{"v":"old"}]'
        # Current value before restore should be snapshotted
        versions = self.db.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersions::test_chapter_service_update_creates_version -v`
Expected: FAIL — `update_chapter` doesn't create versions yet.

- [ ] **Step 3: Implement ChapterService changes**

Replace the full content of `backend/app/services/writer_agent/chapter_service.py`:

```python
"""Chapter CRUD service layer."""
import uuid
from .novel_db import NovelDB


class ChapterService:
    def __init__(self):
        self.db = NovelDB()

    def list_chapters(self, project_id: str) -> list:
        return self.db.list_chapters(project_id)

    def create_chapter(self, project_id: str, title: str, chapter_order: int = None) -> dict:
        chapter_id = f"ch_{uuid.uuid4().hex[:12]}"
        if chapter_order is None:
            chapters = self.db.list_chapters(project_id)
            chapter_order = max((c["chapter_order"] for c in chapters), default=0) + 1
        self.db.create_chapter(project_id, chapter_id, chapter_order, title)
        return {"chapter_id": chapter_id, "chapter_order": chapter_order, "title": title}

    def update_chapter(self, project_id: str, chapter_id: str, **kwargs) -> dict:
        # Snapshot old outline before overwriting
        outline_label = kwargs.pop("outline_label", "")
        if "outline_json" in kwargs:
            ch = self.db.get_chapter_by_id(project_id, chapter_id)
            old_outline = (ch or {}).get("outline_json", "[]")
            if old_outline and old_outline != "[]":
                self.db.save_outline_version(project_id, chapter_id, old_outline, label=outline_label)
        self.db.update_chapter(project_id, chapter_id, **kwargs)
        return {"chapter_id": chapter_id, "updated": True}

    def delete_chapter(self, project_id: str, chapter_id: str):
        self.db.delete_chapter(project_id, chapter_id)

    def list_outline_versions(self, project_id: str, chapter_id: str) -> list:
        return self.db.list_outline_versions(project_id, chapter_id)

    def restore_outline_version(self, project_id: str, chapter_id: str, version_id: str) -> dict:
        target = self.db.get_outline_version(project_id, version_id)
        if not target:
            raise ValueError(f"Version {version_id} not found")
        # Snapshot current value before restoring
        ch = self.db.get_chapter_by_id(project_id, chapter_id)
        current_outline = (ch or {}).get("outline_json", "[]")
        if current_outline and current_outline != "[]":
            self.db.save_outline_version(project_id, chapter_id, current_outline, label="回退前快照")
        self.db.update_chapter(project_id, chapter_id, outline_json=target["outline_json"])
        return {"chapter_id": chapter_id, "restored_version_id": version_id}
```

- [ ] **Step 4: Add `get_chapter_by_id` to NovelDB**

The service needs to look up a chapter by `chapter_id` (not `chapter_order`). Add to `NovelDB` in `novel_db.py`, after the existing `get_chapter` method (around line 988):

```python
    def get_chapter_by_id(
        self,
        project_id: str,
        chapter_id: str,
        include_content: bool = False,
    ) -> dict[str, Any] | None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            if include_content:
                cols = f"cc.*, {self._CHAPTER_META_COLS}"
            else:
                cols = (
                    "cc.chapter_id, cc.project_id, cc.chapter_order, cc.title, "
                    f"cc.word_count, cc.status, cc.created_at, cc.updated_at, "
                    f"{self._CHAPTER_META_COLS}"
                )
            row = conn.execute(
                f"""
                SELECT {cols}
                FROM chapter_content cc
                LEFT JOIN chapter_meta cm ON cm.chapter_id = cc.chapter_id
                WHERE cc.project_id = ? AND cc.chapter_id = ?
                """,
                (project_id, chapter_id),
            ).fetchone()
            return _row_to_dict(row)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersions -v`
Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/writer_agent/novel_db.py backend/app/services/writer_agent/chapter_service.py backend/tests/test_writer_agent.py
git commit -m "feat: ChapterService snapshots outline on save, adds restore"
```

---

### Task 3: API Layer — Add version list and restore endpoints

**Files:**
- Modify: `backend/app/api/writer_agent.py`
- Modify: `frontend/src/api/writerAgent.js`

- [ ] **Step 1: Write the failing test**

Add a new test class to `backend/tests/test_writer_agent.py`:

```python
class TestOutlineVersionAPI:
    """Test outline version API endpoints."""

    TEST_PROJECT = f"__test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)
        self.db.create_chapter(self.TEST_PROJECT, "ch_api", 1, "API章")
        self.db.update_chapter(self.TEST_PROJECT, "ch_api", outline_json='[{"scene_order":1}]')

        os.environ["FLASK_PORT"] = "3888"
        from app import create_app
        app = create_app()
        self.client = app.test_client()
        yield
        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_list_versions_empty(self):
        resp = self.client.get(
            f"/api/writer-agent/chapters/detail/ch_api/outline-versions?project_id={self.TEST_PROJECT}"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"] == []

    def test_save_then_list(self):
        # Save triggers version creation
        self.client.put(
            "/api/writer-agent/chapters/detail/ch_api",
            json={"project_id": self.TEST_PROJECT, "outline_json": '[{"scene_order":2}]', "outline_label": "v1标注"},
        )
        resp = self.client.get(
            f"/api/writer-agent/chapters/detail/ch_api/outline-versions?project_id={self.TEST_PROJECT}"
        )
        data = resp.get_json()
        assert len(data["data"]) == 1
        assert data["data"][0]["label"] == "v1标注"

    def test_restore_version(self):
        # Create a version by saving
        self.client.put(
            "/api/writer-agent/chapters/detail/ch_api",
            json={"project_id": self.TEST_PROJECT, "outline_json": '[{"scene_order":99}]'},
        )
        versions = self.client.get(
            f"/api/writer-agent/chapters/detail/ch_api/outline-versions?project_id={self.TEST_PROJECT}"
        ).get_json()["data"]
        vid = versions[0]["version_id"]
        # Restore
        resp = self.client.post(
            f"/api/writer-agent/chapters/detail/ch_api/outline-versions/{vid}/restore",
            json={"project_id": self.TEST_PROJECT},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # Verify current outline is restored
        chapters = self.client.get(
            f"/api/writer-agent/chapters/{self.TEST_PROJECT}"
        ).get_json()["data"]
        ch = [c for c in chapters if c["chapter_id"] == "ch_api"][0]
        assert ch["outline_json"] == '[{"scene_order":1}]'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersionAPI -v`
Expected: FAIL — 404 on the new endpoints.

- [ ] **Step 3: Add API endpoints**

In `backend/app/api/writer_agent.py`, add after the `update_chapter` endpoint (after line 211):

```python
@writer_agent_bp.route("/chapters/detail/<chapter_id>/outline-versions", methods=["GET"])
def list_outline_versions(chapter_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.chapter_service import ChapterService
        versions = ChapterService().list_outline_versions(project_id, chapter_id)
        return jsonify({"success": True, "data": versions})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/chapters/detail/<chapter_id>/outline-versions/<version_id>/restore", methods=["POST"])
def restore_outline_version(chapter_id, version_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        from ..services.writer_agent.chapter_service import ChapterService
        result = ChapterService().restore_outline_version(project_id, chapter_id, version_id)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)
```

Also whitelist `outline_label` in the existing `update_chapter` endpoint. Change the filter line (line 206-207) from:

```python
            if k in ("title", "summary", "outline_json", "timeline_note", "open_threads_json", "pov_character")
```

to:

```python
            if k in ("title", "summary", "outline_json", "timeline_note", "open_threads_json", "pov_character", "outline_label")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py::TestOutlineVersionAPI -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Add frontend API functions**

In `frontend/src/api/writerAgent.js`, add before the `// Migration` comment (before line 105):

```javascript
// Outline versions
export function getOutlineVersions(chapterId, projectId) {
  return get(`/api/writer-agent/chapters/detail/${chapterId}/outline-versions?project_id=${projectId}`);
}

export function restoreOutlineVersion(chapterId, versionId, projectId) {
  return post(`/api/writer-agent/chapters/detail/${chapterId}/outline-versions/${versionId}/restore`, { project_id: projectId });
}
```

- [ ] **Step 6: Run frontend build**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/writer_agent.py frontend/src/api/writerAgent.js backend/tests/test_writer_agent.py
git commit -m "feat: outline version list and restore API endpoints"
```

---

### Task 4: Frontend — OutlineView version history panel

**Files:**
- Modify: `frontend/src/views/writer/OutlineView.vue`
- Modify: `frontend/src/views/WriterWorkbenchView.vue`

- [ ] **Step 1: Update OutlineView props and emits**

In `frontend/src/views/writer/OutlineView.vue`, update the script section. Replace the existing props and emits:

```javascript
const props = defineProps({
  outline: { type: Array, default: () => [] },
  chapterId: { type: String, default: "" },
  projectId: { type: String, default: "" },
  versions: { type: Array, default: () => [] },       // version metadata list
  previewOutline: { type: Array, default: null },      // read-only preview data
});

const emit = defineEmits(["save", "load-versions", "restore", "cancel-preview"]);
```

- [ ] **Step 2: Add version state and label input**

Add after the `dirty` ref:

```javascript
const showHistory = ref(false);
const labelInput = ref("");
```

- [ ] **Step 3: Update handleSave to include label**

Replace the `handleSave` function:

```javascript
function handleSave() {
  emit("save", JSON.parse(JSON.stringify(localOutline.value)), labelInput.value);
  labelInput.value = "";
}
```

- [ ] **Step 4: Add version panel to template**

Replace the entire `<template>` block of `OutlineView.vue`:

```html
<template>
  <div class="outline-view">
    <div class="outline-header">
      <h3 class="outline-title title-ancient">章节大纲</h3>
      <span class="outline-count">{{ displayOutline.length }} 个场景</span>
      <div class="outline-header-actions">
        <input
          v-if="!previewOutline"
          v-model="labelInput"
          class="outline-label-input"
          placeholder="版本标注（可选）"
        />
        <button
          v-if="!previewOutline"
          class="btn btn-sm outline-save-btn"
          :disabled="!dirty"
          @click="handleSave"
        >保存大纲</button>
        <button
          class="btn btn-sm outline-history-btn"
          :class="{ active: showHistory }"
          @click="toggleHistory"
        >历史版本</button>
      </div>
    </div>

    <!-- Preview banner -->
    <div v-if="previewOutline" class="outline-preview-banner">
      <span>正在预览历史版本</span>
      <button class="btn btn-sm" @click="emit('restore')">回退到此版本</button>
      <button class="btn btn-sm" @click="emit('cancel-preview')">取消预览</button>
    </div>

    <!-- Version history panel -->
    <div v-if="showHistory" class="outline-version-list">
      <div v-if="!versions.length" class="outline-version-empty">暂无历史版本</div>
      <div
        v-for="(ver, idx) in versions"
        :key="ver.version_id"
        class="outline-version-item"
        @click="emit('load-versions', ver.version_id)"
      >
        <span class="outline-version-idx">{{ versions.length - idx }}</span>
        <span class="outline-version-label">{{ ver.label || '自动快照' }}</span>
        <span class="outline-version-time">{{ formatTime(ver.created_at) }}</span>
      </div>
    </div>

    <!-- Scene list (current or preview) -->
    <div class="outline-list">
      <div
        v-for="(scene, idx) in displayOutline"
        :key="idx"
        class="outline-item"
      >
        <div class="outline-item-header">
          <span class="outline-order">{{ scene.scene_order }}</span>
          <input
            v-if="!previewOutline"
            v-model="scene.title"
            class="outline-item-title"
            placeholder="场景标题"
            @input="dirty = true"
          />
          <span v-else class="outline-item-title outline-item-title--readonly">{{ scene.title }}</span>
          <div v-if="!previewOutline" class="outline-item-actions">
            <button class="outline-move-btn" :disabled="idx === 0" @click="moveUp(idx)" title="上移">↑</button>
            <button class="outline-move-btn" :disabled="idx === displayOutline.length - 1" @click="moveDown(idx)" title="下移">↓</button>
            <button class="outline-delete-btn" @click="removeScene(idx)" title="删除">×</button>
          </div>
        </div>

        <div class="outline-item-fields">
          <div class="outline-field">
            <label>POV</label>
            <input v-if="!previewOutline" v-model="scene.pov" placeholder="视角角色" @input="dirty = true" />
            <span v-else class="outline-field-readonly">{{ scene.pov || '—' }}</span>
          </div>
          <div class="outline-field outline-field--wide">
            <label>概述</label>
            <textarea
              v-if="!previewOutline"
              v-model="scene.summary"
              rows="2"
              placeholder="场景概述..."
              @input="dirty = true"
            ></textarea>
            <p v-else class="outline-field-readonly">{{ scene.summary || '—' }}</p>
          </div>
          <div class="outline-field outline-field--wide">
            <label>关键事件</label>
            <div class="outline-events">
              <template v-if="!previewOutline">
                <div v-for="(ev, ei) in scene.key_events" :key="ei" class="outline-event-row">
                  <input
                    :value="ev"
                    @input="updateEvent(idx, ei, $event.target.value)"
                    placeholder="事件描述"
                  />
                  <button class="outline-event-del" @click="removeEvent(idx, ei)">×</button>
                </div>
                <button class="outline-event-add" @click="addEvent(idx)">+ 事件</button>
              </template>
              <template v-else>
                <div v-for="(ev, ei) in scene.key_events" :key="ei" class="outline-event-row">
                  <span class="outline-field-readonly">{{ ev }}</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <button v-if="!previewOutline" class="outline-add-scene" @click="addScene">+ 添加场景</button>
  </div>
</template>
```

- [ ] **Step 5: Add computed and helper in script**

Add after `labelInput` ref:

```javascript
const displayOutline = computed(() => {
  return previewOutline.value || localOutline.value;
});

function toggleHistory() {
  showHistory.value = !showHistory.value;
  if (showHistory.value) {
    emit("load-versions");
  }
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
```

Add `computed` to the Vue import:

```javascript
import { ref, watch, computed } from "vue";
```

Make sure `previewOutline` is accessed properly — Vue 3 `defineProps` returns reactive props, so use `props.previewOutline` via:

```javascript
const previewOutline = computed(() => props.previewOutline);
```

(Add this after the props definition, and use `previewOutline.value` in `displayOutline`.)

- [ ] **Step 6: Add styles for new elements**

Append to the `<style scoped>` block:

```css
.outline-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.outline-label-input {
  width: 140px;
  padding: 5px 10px;
  font-size: 12px;
  border: 1px solid var(--line-medium, #d0ccc4);
  border-radius: 6px;
  outline: none;
  background: #faf9f7;
  color: var(--text-main, #1a1a1a);
}

.outline-label-input:focus {
  border-color: var(--accent-copper, #c09060);
}

.outline-history-btn {
  padding: 6px 12px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--line-medium, #d0ccc4);
  border-radius: 6px;
  color: var(--text-dim, #999);
  cursor: pointer;
}

.outline-history-btn.active,
.outline-history-btn:hover {
  border-color: var(--accent-copper, #c09060);
  color: var(--accent-copper, #c09060);
}

.outline-preview-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: rgba(176, 125, 75, 0.08);
  border: 1px solid var(--accent-copper, #c09060);
  border-radius: 8px;
  font-size: 13px;
  color: var(--accent-copper, #c09060);
}

.outline-version-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;
  padding: 10px;
  background: #faf9f7;
  border: 1px solid var(--line-soft, #e0dcd4);
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.outline-version-empty {
  font-size: 13px;
  color: var(--text-dim, #999);
  text-align: center;
  padding: 8px;
}

.outline-version-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.outline-version-item:hover {
  background: rgba(176, 125, 75, 0.08);
}

.outline-version-idx {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--line-soft, #e0dcd4);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.outline-version-label {
  flex: 1;
  color: var(--text-main, #1a1a1a);
}

.outline-version-time {
  font-size: 11px;
  color: var(--text-dim, #999);
  flex-shrink: 0;
}

.outline-item-title--readonly {
  flex: 1;
  padding: 4px 8px;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-main, #1a1a1a);
}

.outline-field-readonly {
  font-size: 13px;
  color: var(--text-main, #1a1a1a);
  padding: 4px 0;
}
```

- [ ] **Step 7: Run frontend build**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/writer/OutlineView.vue
git commit -m "feat: OutlineView version history panel, preview mode, label input"
```

---

### Task 5: Frontend — Wire versioning into WriterWorkbenchView

**Files:**
- Modify: `frontend/src/views/WriterWorkbenchView.vue`

- [ ] **Step 1: Add imports**

In `WriterWorkbenchView.vue`, update the writerAgent import to include the new functions:

```javascript
import {
  runWriterAgent,
  getScenes,
  updateScene as updateSceneApi,
  deleteScene as deleteSceneApi,
  getPresets,
  createPreset,
  updatePreset,
  deletePreset,
  getChapters,
  migrateProject,
  commitToManuscript,
  getContinuationContext,
  updateChapter,
  getManuscript,
  updateManuscriptBlock,
  tagManuscriptBlocks,
  exportManuscript,
  getOutlineVersions,
  restoreOutlineVersion,
} from "../api/writerAgent.js";
```

- [ ] **Step 2: Add state refs**

Add after `chapterOutlineData` ref:

```javascript
const outlineVersions = ref([]);
const outlinePreview = ref(null); // outline array for preview mode
const outlinePreviewVersionId = ref("");
```

- [ ] **Step 3: Update OutlineView bindings in template**

Update BOTH OutlineView usages in the template to pass the new props and handle new events.

For the **outline tab** OutlineView (around line 216):

```html
<OutlineView
  v-if="chapterOutlineData && chapterOutlineData.length"
  :outline="chapterOutlineData"
  :chapter-id="chapterId"
  :project-id="projectId"
  :versions="outlineVersions"
  :preview-outline="outlinePreview"
  @save="handleOutlineSave"
  @load-versions="handleLoadVersions"
  @restore="handleOutlineRestore"
  @cancel-preview="outlinePreview = null; outlinePreviewVersionId = ''"
/>
```

For the **writing mode** OutlineView (around line 323):

```html
<OutlineView
  v-if="outlineData"
  :outline="outlineData"
  :chapter-id="chapterId"
  :project-id="projectId"
  :versions="outlineVersions"
  :preview-outline="outlinePreview"
  @save="handleOutlineSave"
  @load-versions="handleLoadVersions"
  @restore="handleOutlineRestore"
  @cancel-preview="outlinePreview = null; outlinePreviewVersionId = ''"
/>
```

- [ ] **Step 4: Update handleOutlineSave to pass label**

Replace the `handleOutlineSave` function:

```javascript
async function handleOutlineSave(outline, label = "") {
  if (!projectId.value || !chapterId.value) {
    error.value = "请先选择项目和章节";
    return;
  }
  try {
    await updateChapter(chapterId.value, {
      project_id: projectId.value,
      outline_json: JSON.stringify(outline),
      outline_label: label,
    });
    if (viewMode.value === "outline") {
      chapterOutlineData.value = outline;
    } else {
      outlineData.value = outline;
    }
    message.value = "大纲已保存";
    error.value = "";
  } catch (err) {
    error.value = err.message || "保存大纲失败";
  }
}
```

- [ ] **Step 5: Add version loading and restore handlers**

Add after `handleOutlineSave`:

```javascript
async function handleLoadVersions(versionId) {
  if (!projectId.value || !chapterId.value) return;
  try {
    if (!versionId) {
      // Initial load — fetch version list
      const resp = await getOutlineVersions(chapterId.value, projectId.value);
      outlineVersions.value = resp.data || [];
      return;
    }
    // Load a specific version for preview
    const resp = await getOutlineVersions(chapterId.value, projectId.value);
    outlineVersions.value = resp.data || [];
    // We need to fetch full version — use the list endpoint doesn't include body,
    // so we do a restore-preview by fetching chapter after a temporary no-op.
    // Actually, we need a get-single-version. For now, fetch via list and re-fetch chapter.
    // Simpler: add outline_json to list response for the selected version.
    // Best approach: just call the restore endpoint in preview, or add a get endpoint.
    // For simplicity, fetch the full version via a dedicated get.
    // We don't have a get-single endpoint yet — let's use the restore approach:
    // Actually, let's just add inline fetch. The list doesn't include body.
    // We'll fetch it from a lightweight endpoint. For now, use a workaround:
    // re-fetch all chapters and check if the version_id matches.
    // ACTUALLY: The simplest fix is to include outline_json in the list for the selected item.
    // But that changes the API. Let's add a GET single-version endpoint.
    // For now, since versions are small, include outline_json in list response.
    error.value = "";
  } catch (err) {
    error.value = err.message || "加载版本失败";
  }
}

async function handleOutlineRestore() {
  if (!outlinePreviewVersionId.value || !projectId.value || !chapterId.value) return;
  try {
    await restoreOutlineVersion(chapterId.value, outlinePreviewVersionId.value, projectId.value);
    outlinePreview.value = null;
    outlinePreviewVersionId.value = "";
    // Reload current outline
    if (viewMode.value === "outline") {
      await loadChapterOutline();
    } else {
      // Refetch from DB
      const chapters = await getChapters(projectId.value);
      const list = chapters.data || chapters;
      const ch = list.find(c => c.chapter_id === chapterId.value);
      if (ch?.outline_json) {
        outlineData.value = typeof ch.outline_json === "string" ? JSON.parse(ch.outline_json) : ch.outline_json;
      }
    }
    // Refresh version list
    const resp = await getOutlineVersions(chapterId.value, projectId.value);
    outlineVersions.value = resp.data || [];
    message.value = "已回退到历史版本";
    error.value = "";
  } catch (err) {
    error.value = err.message || "回退失败";
  }
}
```

**Wait — there's a gap.** The version list endpoint doesn't return `outline_json` (by design, to keep it lightweight), so we can't preview a version without an additional endpoint. We need a GET single-version endpoint.

- [ ] **Step 6: Add GET single-version API endpoint**

In `backend/app/api/writer_agent.py`, add after the list endpoint:

```python
@writer_agent_bp.route("/chapters/detail/<chapter_id>/outline-versions/<version_id>", methods=["GET"])
def get_outline_version(chapter_id, version_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        version = svc.db.get_outline_version(project_id, version_id)
        if not version:
            return jsonify({"success": False, "error": "版本不存在"}), 404
        return jsonify({"success": True, "data": version})
    except Exception as exc:
        return _error_response(exc)
```

In `frontend/src/api/writerAgent.js`, add:

```javascript
export function getOutlineVersion(chapterId, versionId, projectId) {
  return get(`/api/writer-agent/chapters/detail/${chapterId}/outline-versions/${versionId}?project_id=${projectId}`);
}
```

Update the import in `WriterWorkbenchView.vue` to include `getOutlineVersion`.

- [ ] **Step 7: Simplify handleLoadVersions**

Replace the `handleLoadVersions` function with the clean version:

```javascript
async function handleLoadVersions(versionId) {
  if (!projectId.value || !chapterId.value) return;
  try {
    if (!versionId) {
      const resp = await getOutlineVersions(chapterId.value, projectId.value);
      outlineVersions.value = resp.data || [];
      return;
    }
    // Load specific version for preview
    const resp = await getOutlineVersion(chapterId.value, versionId, projectId.value);
    const ver = resp.data;
    if (ver?.outline_json) {
      const parsed = typeof ver.outline_json === "string" ? JSON.parse(ver.outline_json) : ver.outline_json;
      outlinePreview.value = Array.isArray(parsed) ? parsed : null;
      outlinePreviewVersionId.value = versionId;
    }
    error.value = "";
  } catch (err) {
    error.value = err.message || "加载版本失败";
  }
}
```

- [ ] **Step 8: Run frontend build**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 9: Run all backend tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py -v`
Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/views/WriterWorkbenchView.vue frontend/src/api/writerAgent.js backend/app/api/writer_agent.py
git commit -m "feat: wire outline version history into workbench UI"
```
