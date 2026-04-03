# Task Cancellation & Enhanced Logging

## 1. Task Cancellation Mechanism

### Problem
Once a seed pipeline starts, it cannot be stopped. Even if the frontend errors out, the backend keeps sending LLM requests in its daemon thread until completion or crash.

### Design: Cooperative Cancellation via TaskStatus

#### Backend

**TaskStatus enum** (`backend/app/models/task.py`):
- Add `CANCELLED = "cancelled"` status

**TaskManager** (`backend/app/models/task.py`):
- Add `cancel_task(task_id)` method that sets status to `CANCELLED`
- Only cancels tasks in `PROCESSING` state; returns False otherwise

**TaskCancelledException** (`backend/app/services/task_cancelled.py`):
- New exception class raised when cancellation is detected
- Carries `task_id` and `stage` for logging

**Cancel API endpoint** (`backend/app/api/project.py`):
- `POST /api/project/task/<task_id>/cancel`
- Returns 200 with `{"success": true, "status": "cancelled"}` on success
- Returns 400 if task is not in a cancellable state

**Cancellation checks — SequentialReader** (`backend/app/services/sequential_reader.py`):
- Accept `task_id` and `task_manager` parameters
- Before each segment read, check `task_manager.get_task(task_id).status`
- If status is `CANCELLED`, raise `TaskCancelledException`
- This is the main checkpoint since sequential reading is the longest stage (10-75%)

**Cancellation checks — SeedExtractRunner** (`backend/app/services/seed_extract_runner.py`):
- Add `_check_cancelled()` method that checks task status
- Call it between stages (after smart_segmentation, after sequential_reading, after global_integration)
- Catch `TaskCancelledException` in `run()`: save whatever artifacts exist, set project status to FAILED with error "用户取消了分析任务"

**Cancellation checks — CharacterAgentProfileGenerator** (`backend/app/services/character_agent_profile_generator.py`):
- Accept optional `cancelled_check` callback
- Check before submitting each character to the thread pool
- If cancelled, skip remaining characters and return partial results

**Data preservation on cancel:**
- All artifacts written to disk before the cancel point are preserved
- `reading_notes.json` is saved after each segment completes (already implemented)
- `seed_analysis.json` may not exist if cancelled before global_integration
- Project status → `FAILED`, error → "用户取消了分析任务"
- Task status → `CANCELLED`

#### Frontend

**Cancel button** (`frontend/src/views/overview/SeedUploadFormFields.vue` or parent):
- Show "取消分析" button when `uploadPhase === "processing"`
- Click triggers confirmation dialog: "确定要取消当前分析任务吗？已完成的分析数据将保留。"
- On confirm: call `POST /api/project/task/<task_id>/cancel`
- On success: stop polling, update UI to show cancelled state

**useSeedUpload composable** (`frontend/src/composables/useSeedUpload.js`):
- Add `cancelUpload()` method
- Calls cancel API, then sets `uploadPhase = "error"`, `taskStatus = "cancelled"`
- Exported alongside other methods

**Pipeline visualization**:
- `cancelled` task status treated like `failed` for node state rendering (no changes needed — existing `failed` handling covers it)

## 2. Enhanced Per-Task Logging

### Problem
Runtime logs go to a shared daily log file with no per-task isolation. SequentialReader barely logs anything. LLM calls are not logged. Debugging pipeline failures requires guessing.

### Design: TaskFileLogger with Structured Records

**TaskFileLogger** (`backend/app/utils/task_file_logger.py`):
- Creates a log file at `projects/<project_id>/task_logs/<task_id>.log`
- Format: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [stage] message`
- LLM call details logged as indented JSON blocks
- Uses standard Python `logging.FileHandler` with UTF-8 encoding
- Also logs to the existing global logger (dual output)

```
[2026-04-03 14:23:01] [INFO] [extract_text] 开始提取文本，共 2 份文稿
[2026-04-03 14:23:02] [INFO] [smart_segmentation] 智能分段完成，共 5 个阅读段
[2026-04-03 14:23:03] [INFO] [sequential_reading] 开始精读段 seg_001（1/5）
[2026-04-03 14:23:15] [INFO] [sequential_reading] LLM 调用完成
  {
    "module": "sequential_reading",
    "model": "deepseek-chat",
    "elapsed_ms": 12400,
    "prompt_preview": "你是一名专业的小说分析师...(前500字符)",
    "response_preview": "{\"segment_summary\": \"沈夜在镜湖...(前1000字符)",
    "prompt_chars": 35000,
    "response_chars": 4200
  }
[2026-04-03 14:23:15] [INFO] [sequential_reading] 段 seg_001 完成，耗时 12.4s，新增角色 3 个
[2026-04-03 14:25:30] [WARN] [sequential_reading] 任务已取消，停止在段 seg_003
```

**Integration points:**

1. **SeedExtractRunner** (`backend/app/services/seed_extract_runner.py`):
   - Create `TaskFileLogger` in constructor
   - Log stage transitions with timing
   - Log final result or error
   - Pass logger to sub-services

2. **SequentialReader** (`backend/app/services/sequential_reader.py`):
   - Accept optional `task_logger` parameter
   - Log per-segment: start, LLM call details, merge results summary, end + elapsed time
   - Log arc summary generation

3. **CharacterAgentProfileGenerator** (`backend/app/services/character_agent_profile_generator.py`):
   - Accept optional `task_logger` parameter
   - Log per-character profile generation: name, elapsed time, success/failure

4. **LLM call logging wrapper**:
   - TaskFileLogger provides `log_llm_call(module, model, prompt, response, elapsed_ms)` method
   - Truncates prompt to 500 chars and response to 1000 chars
   - Calculates and logs character counts for full content

## 3. File Inventory

### New Files
- `backend/app/services/task_cancelled.py` — TaskCancelledException
- `backend/app/utils/task_file_logger.py` — TaskFileLogger
- `backend/tests/test_task_cancellation.py` — cancellation tests
- `backend/tests/test_task_file_logger.py` — logger tests

### Modified Files
- `backend/app/models/task.py` — add CANCELLED status, cancel_task method
- `backend/app/api/project.py` — add cancel endpoint
- `backend/app/services/seed_extract_runner.py` — cancellation checks, logger integration
- `backend/app/services/sequential_reader.py` — cancellation check between segments, logging
- `backend/app/services/character_agent_profile_generator.py` — cancellation check, logging
- `frontend/src/composables/useSeedUpload.js` — cancelUpload method
- `frontend/src/views/overview/SeedUploadFormFields.vue` (or parent component) — cancel button with confirmation dialog
