"""深度阅读无感自动重试的契约测试。

覆盖:
  - L1 瞬态重试 → 最终成功,没有错误级 timeline 事件
  - 永久错误(鉴权/模型不存在)→ PermanentLLMError 透传
  - 耗尽重试预算 → 段落 status=retry_needed,流水线继续
  - 连续失败触发 L2 stage_cooldown 事件
  - L3 扫尾 → 失败段在主循环后被简化 prompt 恢复
  - 聚合器跳过 retry_needed 段
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from openai import APIStatusError, APITimeoutError

from app.services.reading_notes_manager import ReadingNotesManager
from app.services.seed_analysis_aggregator import SeedAnalysisAggregator
from app.services.sequential_reader import SequentialReader, MODULE_KEY
from app.utils.retry_policy import (
    ExhaustedLLMRetries,
    PermanentLLMError,
    RetryPolicy,
    classify_llm_error,
    retry_with_policy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEGMENT_RESULT = {
    "segment_summary": "沈夜在这一段展现冷静。",
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


def _make_segment(index: int) -> Dict[str, Any]:
    seg_id = f"seg_{index:03d}"
    return {
        "segment_id": seg_id,
        "chapters": [
            {
                "chapter_id": f"ch_{index:03d}",
                "order": index,
                "title": f"第{index}章",
                "content": f"沈夜在第{index}章出场。",
                "word_count": 20,
            }
        ],
    }


class _ScriptedClient:
    """按预设脚本模拟 LLM client.chat_json_value 的成功/异常序列。"""

    def __init__(self, per_segment_plans: Dict[str, List[Any]]):
        self._plans = {k: list(v) for k, v in per_segment_plans.items()}
        self.call_log: List[Dict[str, Any]] = []

    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        # 从 user 消息中抽取 segment_id 线索(我们把段落文本里写了第 N 章)
        content = ""
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                break
        seg_key = self._infer_key(content)
        self.call_log.append({
            "seg_key": seg_key,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        plan = self._plans.get(seg_key)
        if not plan:
            return dict(_SEGMENT_RESULT)
        next_action = plan.pop(0)
        if isinstance(next_action, Exception):
            raise next_action
        return next_action

    def _infer_key(self, content: str) -> str:
        # 段落:内容里包含 "第 N 章"。弧线:包含 "arc"。卷:包含 "volume"。
        if "arc" in content.lower() or "弧线" in content:
            return "arc"
        if "volume" in content.lower() or "卷" in content:
            return "volume"
        for idx in range(1, 60):
            if f"第{idx}章" in content:
                return f"seg_{idx:03d}"
        return "default"


class _Router:
    def __init__(self, client):
        self._client = client

    def build_client(self, module_key: str):
        assert module_key == MODULE_KEY
        return self._client


def _transient_timeout() -> APITimeoutError:
    # APITimeoutError(request) 需要一个 request 对象;构造最简单的替身。
    import httpx
    return APITimeoutError(httpx.Request("POST", "https://example.com"))


def _fake_api_status_error(status_code: int, message: str) -> APIStatusError:
    import httpx
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    try:
        return APIStatusError(message, response=response, body={"error": message})
    except TypeError:
        # 旧 SDK 兼容
        return APIStatusError(message, response=response)


# ---------------------------------------------------------------------------
# retry_policy 本身的单元测试
# ---------------------------------------------------------------------------

def test_classify_llm_error_variants():
    assert classify_llm_error(_transient_timeout())[0] == "transient"
    auth = _fake_api_status_error(401, "invalid api key")
    assert classify_llm_error(auth)[0].startswith("permanent")
    not_found = _fake_api_status_error(404, "model_not_found")
    assert classify_llm_error(not_found)[0].startswith("permanent")
    content = ValueError("failed to parse JSON after 3 attempts")
    assert classify_llm_error(content)[0] == "content"


def test_retry_with_policy_succeeds_after_transient():
    calls = []

    def fn(attempt):
        calls.append(attempt)
        if attempt == 0:
            raise _transient_timeout()
        return "ok"

    result = retry_with_policy(
        fn,
        policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
        sleep=lambda _s: None,
    )
    assert result == "ok"
    assert calls == [0, 1]


def test_retry_with_policy_permanent_fast_fails():
    def fn(attempt):
        raise _fake_api_status_error(401, "unauthorized")

    with pytest.raises(PermanentLLMError) as excinfo:
        retry_with_policy(
            fn,
            policy=RetryPolicy(max_attempts=5, base_delay_seconds=0, max_delay_seconds=0),
            sleep=lambda _s: None,
        )
    assert excinfo.value.error_class == "permanent_auth"


def test_retry_with_policy_exhausts_and_notifies():
    on_retry_events = []

    def fn(attempt):
        raise _transient_timeout()

    def on_retry(attempt, max_attempts, wait, ec, exc):
        on_retry_events.append((attempt, max_attempts, ec))

    with pytest.raises(ExhaustedLLMRetries):
        retry_with_policy(
            fn,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
            on_retry=on_retry,
            sleep=lambda _s: None,
        )
    # on_retry 每次重试前各触发一次:attempt 1 和 2
    assert [e[0] for e in on_retry_events] == [1, 2]


# ---------------------------------------------------------------------------
# SequentialReader 场景测试
# ---------------------------------------------------------------------------

def _reader(policy: RetryPolicy, **kwargs) -> tuple[SequentialReader, _ScriptedClient]:
    client = kwargs.pop("client", None)
    if client is None:
        client = _ScriptedClient({})
    reader = SequentialReader(
        llm_router=_Router(client),
        arc_interval=kwargs.pop("arc_interval", 100),
        retry_policy=policy,
        cooldown_streak=kwargs.pop("cooldown_streak", 2),
        cooldown_seconds=kwargs.pop("cooldown_seconds", 0),
        sweep_enabled=kwargs.pop("sweep_enabled", True),
    )
    return reader, client


def test_segment_transient_error_recovers_silently(monkeypatch):
    client = _ScriptedClient(
        {
            "seg_001": [_transient_timeout(), dict(_SEGMENT_RESULT)],
        }
    )
    reader, _ = _reader(
        RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
        client=client,
    )
    events = []
    reader.read(
        [_make_segment(1)], use_llm=True,
        progress_callback=lambda ev, data: events.append((ev, data)),
    )
    manager_summaries = [e for e in events if e[0] == "segment_permanent_failure"]
    assert not manager_summaries, "瞬态错误不应触发永久失败事件"
    retry_events = [e for e in events if e[0] == "segment_retry"]
    assert len(retry_events) == 1
    assert retry_events[0][1]["scope"] == "segment"


def test_permanent_error_raises_without_burning_budget():
    client = _ScriptedClient(
        {
            "seg_001": [_fake_api_status_error(401, "unauthorized: invalid api key")],
        }
    )
    reader, _ = _reader(
        RetryPolicy(max_attempts=5, base_delay_seconds=0, max_delay_seconds=0),
        client=client,
    )
    with pytest.raises(PermanentLLMError):
        reader.read([_make_segment(1)], use_llm=True)
    # 只应调用一次:永久错误立即抛出
    assert len(client.call_log) == 1


def test_exhausted_segment_is_marked_retry_needed():
    # 所有段级 + 扫尾调用都失败
    client = _ScriptedClient(
        {
            "seg_001": [
                _transient_timeout(),
                _transient_timeout(),
                _transient_timeout(),  # sweep 的最后一次尝试
            ],
        }
    )
    reader, _ = _reader(
        RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
        client=client,
        cooldown_seconds=0,
    )
    events = []
    manager = reader.read(
        [_make_segment(1)], use_llm=True,
        progress_callback=lambda ev, data: events.append((ev, data)),
    )
    failed = manager.failed_segment_ids()
    assert failed == ["seg_001"]
    entry = manager.all_segment_summaries[0]
    assert entry["status"] == "retry_needed"
    assert entry["error_class"] == "transient"
    perm_events = [e for e in events if e[0] == "segment_permanent_failure"]
    assert len(perm_events) == 1


def test_cooldown_emitted_after_consecutive_failures():
    client = _ScriptedClient(
        {
            "seg_001": [_transient_timeout(), _transient_timeout(), _transient_timeout()],
            "seg_002": [_transient_timeout(), _transient_timeout(), _transient_timeout()],
            "seg_003": [dict(_SEGMENT_RESULT)],
        }
    )
    slept: List[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    import app.services.sequential_reader as sr_mod
    original_sleep = sr_mod.time.sleep
    sr_mod.time.sleep = fake_sleep
    try:
        reader, _ = _reader(
            RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
            client=client,
            cooldown_streak=2,
            cooldown_seconds=7.5,
            sweep_enabled=False,
        )
        events = []
        reader.read(
            [_make_segment(1), _make_segment(2), _make_segment(3)],
            use_llm=True,
            progress_callback=lambda ev, data: events.append((ev, data)),
        )
    finally:
        sr_mod.time.sleep = original_sleep

    cooldowns = [e for e in events if e[0] == "stage_cooldown"]
    assert len(cooldowns) == 1
    assert cooldowns[0][1]["wait_seconds"] == 7.5
    assert 7.5 in slept


def test_l3_sweep_recovers_failed_segment():
    client = _ScriptedClient(
        {
            "seg_001": [
                _transient_timeout(),
                _transient_timeout(),  # L1 耗尽
                dict(_SEGMENT_RESULT),  # 扫尾调用成功
            ],
        }
    )
    reader, _ = _reader(
        RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
        client=client,
        cooldown_seconds=0,
    )
    events = []
    manager = reader.read(
        [_make_segment(1)], use_llm=True,
        progress_callback=lambda ev, data: events.append((ev, data)),
    )
    # 段落应被恢复,不再保留 retry_needed 状态
    assert manager.failed_segment_ids() == []
    entry = manager.all_segment_summaries[0]
    assert entry.get("status") != "retry_needed"
    recovered = [e for e in events if e[0] == "segment_sweep_recovered"]
    assert len(recovered) == 1


# ---------------------------------------------------------------------------
# 聚合器跳过 retry_needed
# ---------------------------------------------------------------------------

def test_aggregator_skips_retry_needed_segments():
    manager = ReadingNotesManager()
    manager.add_segment_summary("seg_001", "正常摘要一")
    manager.add_segment_summary(
        "seg_002", "",
        status="retry_needed",
        error_class="transient",
        error_detail="timeout",
    )
    manager.add_segment_summary("seg_003", "正常摘要三")

    aggregator = SeedAnalysisAggregator()
    result = aggregator.aggregate_from_reading_notes(
        manager=manager,
        analysis_goal="测试目标",
        project_name="测试项目",
    )
    beats = result["chapter_beats"]
    assert len(beats) == 2
    assert all("失败" not in b["summary"] for b in beats)
    assert result["source_stats"]["block_count"] == 2
    assert "1 个段落等待手动重读" in result["analysis_summary"]


def test_reading_notes_roundtrip_preserves_status(tmp_path):
    path = tmp_path / "notes.json"
    manager = ReadingNotesManager()
    manager.add_segment_summary("seg_001", "")
    # 手动打上 retry_needed 状态
    manager.all_segment_summaries[-1]["status"] = "retry_needed"
    manager.all_segment_summaries[-1]["error_class"] = "transient"
    manager.save(str(path))

    loaded = ReadingNotesManager.load(str(path))
    assert loaded.failed_segment_ids() == ["seg_001"]

    assert loaded.update_segment_summary("seg_001", "已恢复的摘要")
    assert loaded.failed_segment_ids() == []
    entry = loaded.all_segment_summaries[0]
    assert entry["summary"] == "已恢复的摘要"
    assert "status" not in entry
