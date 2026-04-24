"""断点续传完整性契约测试（F1 / F2 / F3）。

覆盖修好的三件事:
  1. 未处理段（abrupt-kill 路径：smart_segments 里有但 reading_notes 没有
     对应条目）走 retry 时 LLM 结果必须被 add_segment_summary 持久化，
     而不是被 update_segment_summary 返回 False 后悄悄丢掉。
  2. retry 顺序严格按 smart_segments 的时间序，保证 all_segment_summaries
     被追加后依然是小说叙事顺序。
  3. retry 全部段落成功后，要补齐弧线摘要（循环补 + 末尾兜底弧），并在
     达到阈值时一并补卷摘要。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

import pytest

from app.config import Config
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.task import TaskManager
from app.services.reading_notes_manager import ReadingNotesManager
from app.services.seed_extract_runner import SeedExtractRunner
from app.services.seed_extract_task_service import SeedExtractTaskService
from app.services.sequential_reader import MODULE_KEY, SequentialReader
from app.utils.retry_policy import RetryPolicy


_SEGMENT_RESULT_TEMPLATE = {
    "segment_summary": "段落摘要占位",
    "character_updates": [
        {
            "name": "沈夜",
            "identity": "主角",
            "status": "alive",
            "personality_traits": ["冷静"],
        }
    ],
    "narrative_phase": "铺垫",
}

_ARC_RESULT = {"arc_summary": "弧线摘要"}
_VOLUME_RESULT = {"volume_summary": "卷摘要"}


class _ScriptedClient:
    """Returns canned JSON keyed off the prompt content (seg_id / arc / volume)."""

    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        system_content = ""
        user_content = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            elif msg.get("role") == "user":
                user_content = msg.get("content", "")
        if "弧线摘要" in system_content and "卷摘要" not in system_content:
            return dict(_ARC_RESULT)
        if "卷摘要" in system_content:
            return dict(_VOLUME_RESULT)
        # Segment prompt — look at the【本段正文】block (not 前情上下文) to
        # figure out which seg_id is being retried.
        seg_text = user_content
        for marker in ("【本段正文】", "【本段正文（首段，暂无前情）】"):
            idx = user_content.find(marker)
            if idx >= 0:
                seg_text = user_content[idx + len(marker):]
                break
        seg_id = ""
        for idx in range(1, 100):
            m = f"seg_{idx:03d}"
            if m in seg_text:
                seg_id = m
                break
        result = dict(_SEGMENT_RESULT_TEMPLATE)
        result["segment_summary"] = f"{seg_id} 的摘要"
        return result


class _Router:
    def __init__(self, client):
        self._client = client

    def build_client(self, module_key: str):
        assert module_key == MODULE_KEY
        return self._client


class _StubService(SeedExtractTaskService):
    """Skip parent __init__ so it doesn't try to build a real LLM router."""

    def __init__(self, sequential_reader: SequentialReader) -> None:
        self.task_manager = TaskManager()
        self.sequential_reader = sequential_reader


@pytest.fixture
def project_setup(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(
        ProjectManager, "PROJECTS_DIR", str(upload_dir / "projects"),
    )
    TaskManager._instance = None

    project_id = "proj_retry_completeness"
    project_dir = upload_dir / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    project = Project(
        project_id=project_id,
        name="续跑完整性测试",
        status=ProjectStatus.SEED_PROCESSING,
        created_at=now,
        updated_at=now,
        analysis_goal="",
    )
    ProjectManager.save_project(project)
    yield project_id, project_dir
    TaskManager._instance = None


def _write_smart_segments(project_dir, count: int) -> List[Dict[str, Any]]:
    segments = []
    for i in range(1, count + 1):
        segments.append({
            "segment_id": f"seg_{i:03d}",
            "chapters": [
                {
                    "chapter_id": f"ch_{i:03d}",
                    "order": i,
                    "title": f"第{i}章",
                    "content": f"seg_{i:03d} 段落正文内容",
                    "word_count": 10,
                }
            ],
            "chapter_range": str(i),
            "estimated_tokens": 20,
        })
    (project_dir / "smart_segments.json").write_text(
        json.dumps({"segments": segments}, ensure_ascii=False),
        encoding="utf-8",
    )
    return segments


def _build_runner(service: _StubService, project_id: str, monkeypatch) -> SeedExtractRunner:
    task_id = asyncio.run(
        service.task_manager.create_task(
            task_type="seed_retry_segments",
            metadata={"project_id": project_id},
        )
    )
    runner = SeedExtractRunner(service, task_id, use_llm=True, project_id=project_id)
    monkeypatch.setattr(runner, "_validate_llm_modules", lambda: None)
    # 下游 finalize 会调真 LLM（ontology / agent profiles），跳过。
    monkeypatch.setattr(
        runner, "_global_integration_and_ontology",
        lambda *a, **kw: ({"analysis_summary": "stub"}, {"entity_types": [], "edge_types": []}),
    )
    monkeypatch.setattr(
        runner, "_generate_agent_profiles",
        lambda project_id, manager: {"profile_count": 0, "profiles": []},
    )
    monkeypatch.setattr(runner, "_record_unified_db_ready", lambda: None)
    monkeypatch.setattr(runner, "_link_global_data", lambda project_id: None)
    monkeypatch.setattr(runner.service, "_finalize_project", lambda *a, **kw: None)
    return runner


def test_retry_upserts_unprocessed_segments_and_orders_by_smart_segments(
    project_setup, monkeypatch,
):
    """F1 + F2: 首跑在 seg_004 前被杀，checkpoint 记录了 seg_001..seg_004（中间
    seg_003 是 retry_needed），seg_005 / seg_006 从未被处理过。retry 之后
    all_segment_summaries 必须覆盖全部 6 段且按 seg_001..seg_006 时间序。
    （关键 F1 bug: seg_005 / seg_006 走 update_segment_summary 会返回 False,
    旧实现会把 LLM 的结果静默丢掉。）"""
    project_id, project_dir = project_setup
    _write_smart_segments(project_dir, count=6)

    # Pre-state — 与生产"进程被杀"一致：已处理段落按时间序排，seg_003 失败
    # 留在原位，seg_005 / seg_006 完全缺席。
    manager = ReadingNotesManager(arc_interval=100)  # 只考 F1/F2
    manager.add_segment_summary("seg_001", "老摘要 001")
    manager.add_segment_summary("seg_002", "老摘要 002")
    manager.add_segment_summary("seg_003", "", status="retry_needed", error_class="transient")
    manager.add_segment_summary("seg_004", "老摘要 004")
    manager.save(str(project_dir / "reading_notes.json"))

    client = _ScriptedClient()
    reader = SequentialReader(
        llm_router=_Router(client),
        arc_interval=100,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        sweep_enabled=False,
    )
    service = _StubService(reader)
    runner = _build_runner(service, project_id, monkeypatch)

    runner.retry_failed_segments(project_id)

    reloaded = ReadingNotesManager.load(str(project_dir / "reading_notes.json"))
    ids = [e["segment_id"] for e in reloaded.all_segment_summaries]

    # 全 6 段都在，按时间序（F1 修好以后 seg_005 / seg_006 才会真的落盘）
    assert ids == [
        "seg_001", "seg_002", "seg_003",
        "seg_004", "seg_005", "seg_006",
    ], f"Expected time-ordered segment ids, got {ids}"

    # 没有残留的 retry_needed
    assert reloaded.failed_segment_ids() == []

    # seg_003 / seg_005 / seg_006 应被当前 LLM 摘要覆盖，不再是空字符串 / 老值
    summaries_by_id = {e["segment_id"]: e["summary"] for e in reloaded.all_segment_summaries}
    assert summaries_by_id["seg_003"] == "seg_003 的摘要"
    assert summaries_by_id["seg_005"] == "seg_005 的摘要"
    assert summaries_by_id["seg_006"] == "seg_006 的摘要"

    # unprocessed 段的结构化字段也走了 _merge_structured_fields
    assert "沈夜" in reloaded.notes["core_facts"]["characters"]


def test_retry_backfills_arc_and_volume_summaries(project_setup, monkeypatch):
    """F3: retry 成功填满段落后，应当按 arc_interval / volume_arc_threshold
    循环补齐弧摘要 / 卷摘要。arc_interval=2 + 6 段 → 3 条弧摘要；
    volume_arc_threshold=2 → 累计到 2 条弧时补第一个卷摘要，后面再补一次。"""
    project_id, project_dir = project_setup
    _write_smart_segments(project_dir, count=6)

    # 首跑全挂 —— 所有 6 段都是 unprocessed。
    manager = ReadingNotesManager(arc_interval=2, volume_arc_threshold=2)
    manager.save(str(project_dir / "reading_notes.json"))

    client = _ScriptedClient()
    reader = SequentialReader(
        llm_router=_Router(client),
        arc_interval=2,
        volume_arc_threshold=2,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        sweep_enabled=False,
    )
    service = _StubService(reader)
    runner = _build_runner(service, project_id, monkeypatch)

    runner.retry_failed_segments(project_id)

    reloaded = ReadingNotesManager.load(str(project_dir / "reading_notes.json"))

    # 6 段 / arc_interval=2 → 3 条 arc
    arc_summaries = reloaded.notes["plot_state"]["arc_summaries"]
    assert len(arc_summaries) == 3, (
        f"expected 3 arc summaries after retry backfill, got {len(arc_summaries)}: "
        f"{[a.get('arc_id') for a in arc_summaries]}"
    )
    assert [a["arc_id"] for a in arc_summaries] == ["arc_001", "arc_002", "arc_003"]

    # _arc_cursor 推到全部 6 段
    assert reloaded._arc_cursor == 6

    # volume_arc_threshold=2，跑到第 2 / 4 条弧时各触发一次卷摘要
    # while 循环跑 arc_001 / arc_002 后 needs_volume_summary True → vol_001；
    # 再跑 arc_003（尾段兜底），此时 arc_summaries 长度 = 3 >= threshold=2 → vol_002。
    volume_summaries = reloaded.notes["plot_state"]["volume_summaries"]
    assert len(volume_summaries) == 2, (
        f"expected 2 volume summaries, got {len(volume_summaries)}: "
        f"{[v.get('volume_id') for v in volume_summaries]}"
    )
    assert [v["volume_id"] for v in volume_summaries] == ["vol_001", "vol_002"]


def test_retry_skips_arc_backfill_when_nothing_new_to_cover(
    project_setup, monkeypatch,
):
    """Sanity check: 没有新段可补（所有段已覆盖并已出弧摘要）时，backfill 不应
    抛异常也不应额外调用 LLM 生成弧。"""
    project_id, project_dir = project_setup
    _write_smart_segments(project_dir, count=2)

    # 两段都完成，且弧摘要已经把 cursor 推到末尾
    manager = ReadingNotesManager(arc_interval=2, volume_arc_threshold=10)
    manager.add_segment_summary("seg_001", "done 001")
    manager.add_segment_summary("seg_002", "done 002")
    manager.add_arc_summary(
        "arc_001", "既有弧线", [
            {"segment_id": "seg_001"}, {"segment_id": "seg_002"},
        ],
    )
    manager.save(str(project_dir / "reading_notes.json"))

    client = _ScriptedClient()
    reader = SequentialReader(
        llm_router=_Router(client),
        arc_interval=2,
        volume_arc_threshold=10,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        sweep_enabled=False,
    )
    service = _StubService(reader)
    runner = _build_runner(service, project_id, monkeypatch)

    # 没有 failed 也没有 unprocessed → retry 应该直接走 "没有需要重读的段落" 分支
    runner.retry_failed_segments(project_id)

    reloaded = ReadingNotesManager.load(str(project_dir / "reading_notes.json"))
    # 弧线数量保持 1，没有被 backfill 多造一条
    assert len(reloaded.notes["plot_state"]["arc_summaries"]) == 1
