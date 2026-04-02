"""剧情锚点摘要构建器。"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .anchor_point_line_protocol import AnchorPointLineProtocolExecutor
from .anchor_point_prompts import ANCHOR_POINT_SYSTEM_PROMPT
from .sentence_atlas_builder import build_sentence_atlas, build_sentence_map
from .llm_router import LlmRouter
from .local_block_fact_support import split_sentences
from .seed_stage_fallback_support import attach_rule_fallback, should_use_rule_fallback, summarize_stage_failure
from .seed_stage_settings import ANCHOR_INTERVAL


WORLD_STATE_FIELDS = (
    "active_characters",
    "active_organizations",
    "key_relationships",
    "open_plot_threads",
    "recent_events_summary",
)
logger = logging.getLogger(__name__)


class AnchorPointBuilder:
    """在并发提取前生成定距剧情锚点。"""

    MODULE_KEY = "anchor_point_summary"
    DEFAULT_ANCHOR_INTERVAL = ANCHOR_INTERVAL

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()

    def build(
        self,
        blocks: Sequence[Dict[str, Any]],
        chapters: Sequence[Dict[str, Any]],
        skeleton: Dict[str, Any],
        sentence_atlas: Optional[Sequence[Dict[str, Any]]] = None,
        anchor_interval: int = DEFAULT_ANCHOR_INTERVAL,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        if sentence_atlas is None:
            _, sentence_atlas = build_sentence_atlas(chapters)
        chapter_map = {chapter["chapter_id"]: chapter for chapter in chapters}
        sentence_map = build_sentence_map(sentence_atlas)
        sketch_map = {item["chapter_id"]: item for item in skeleton.get("chapter_sketches", [])}
        anchors = []
        cumulative_state = self._empty_world_state()
        for index, anchor_blocks in enumerate(self._group_blocks(blocks, anchor_interval), start=1):
            anchor_meta = self._anchor_meta(index, anchor_blocks, chapter_map)
            if progress_callback:
                progress_callback("start", anchor_meta)
            anchor = self._build_anchor(anchor_meta, anchor_blocks, chapter_map, sketch_map, cumulative_state, sentence_map)
            cumulative_state = self._merge_world_state(cumulative_state, anchor["world_state"])
            anchor["world_state"] = cumulative_state
            anchors.append(anchor)
            if progress_callback:
                progress_callback("complete", anchor)
        return {"anchor_count": len(anchors), "anchors": anchors}

    def nearest_anchor(
        self,
        block_id: str,
        anchors: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        block_order = self._block_order(block_id)
        visible = [item for item in anchors if item.get("end_block_order", 0) < block_order]
        if not visible:
            return None
        return max(visible, key=lambda item: item.get("end_block_order", 0))

    def _build_anchor(
        self,
        anchor_meta: Dict[str, Any],
        blocks: Sequence[Dict[str, Any]],
        chapter_map: Dict[str, Dict[str, Any]],
        sketch_map: Dict[str, Dict[str, Any]],
        previous_state: Dict[str, Any],
        sentence_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
            message = self._build_prompt(blocks, chapter_map, sketch_map, previous_state, sentence_map)
            if hasattr(client, "chat"):
                valid_sentence_ids = [chapter_id for block in blocks for chapter_id in block.get("owned_sentence_ids", [])]
                payload = AnchorPointLineProtocolExecutor(client, sentence_map, valid_sentence_ids).build(message)
                world_state = self._merge_world_state(previous_state, payload)
                return {**anchor_meta, "world_state": world_state}
            payload = client.chat_json_value(
                messages=[
                    {"role": "system", "content": ANCHOR_POINT_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                temperature=0.15,
                max_tokens=4096,
            )
            value = normalize_json_object(payload, "剧情锚点摘要")
            world_state = self._merge_world_state(previous_state, value.get("world_state") or value)
            return {**anchor_meta, "world_state": world_state}
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            logger.warning("剧情锚点生成转为规则回退 (%s): %s", anchor_meta.get("anchor_id", ""), summarize_stage_failure(exc))
            fallback_state = self._fallback_world_state(blocks, chapter_map, sketch_map, previous_state)
            return attach_rule_fallback({**anchor_meta, "world_state": fallback_state}, exc)

    def _build_prompt(
        self,
        blocks: Sequence[Dict[str, Any]],
        chapter_map: Dict[str, Dict[str, Any]],
        sketch_map: Dict[str, Dict[str, Any]],
        previous_state: Dict[str, Any],
        sentence_map: Dict[str, Dict[str, Any]],
    ) -> str:
        chapter_ids = [chapter_id for block in blocks for chapter_id in block.get("owned_chapter_ids", [])]
        fingerprints = [sketch_map.get(chapter_id, {}) for chapter_id in chapter_ids]
        snippets = [self._chapter_snippet(chapter_map[chapter_id]) for chapter_id in chapter_ids if chapter_id in chapter_map]
        lines = [self._fingerprint_line(item) for item in fingerprints if item]
        sentence_catalog = self._sentence_catalog([sentence_id for block in blocks for sentence_id in block.get("owned_sentence_ids", [])], sentence_map)
        return (
            f"## 前一个锚点的世界状态\n{previous_state}\n\n"
            f"## 当前区间章节指纹\n" + ("\n".join(lines) or "无") + "\n\n"
            f"## 当前区间关键段落\n" + ("\n".join(snippets) or "无") + "\n\n"
            f"## 当前区间句子编号\n{sentence_catalog or '无'}"
        )

    def _anchor_meta(
        self,
        index: int,
        blocks: Sequence[Dict[str, Any]],
        chapter_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        chapter_ids = [chapter_id for block in blocks for chapter_id in block.get("owned_chapter_ids", [])]
        chapter_orders = [chapter_map[chapter_id].get("order", 0) for chapter_id in chapter_ids if chapter_id in chapter_map]
        return {
            "anchor_id": f"anchor_{index:04d}",
            "block_range": [block["block_id"] for block in blocks],
            "start_block_order": blocks[0].get("order", 0),
            "end_block_order": blocks[-1].get("order", 0),
            "chapter_range": {
                "start": min(chapter_orders) if chapter_orders else 0,
                "end": max(chapter_orders) if chapter_orders else 0,
            },
        }

    def _group_blocks(
        self,
        blocks: Sequence[Dict[str, Any]],
        anchor_interval: int,
    ) -> List[Sequence[Dict[str, Any]]]:
        ordered = sorted(blocks, key=lambda item: item.get("order", 0))
        return [ordered[index:index + anchor_interval] for index in range(0, len(ordered), anchor_interval)]

    def _chapter_snippet(self, chapter: Dict[str, Any]) -> str:
        sentences = split_sentences(chapter.get("content", ""))
        if not sentences:
            return chapter.get("title", chapter.get("chapter_id", ""))
        if len(sentences) == 1:
            text = sentences[0]
        else:
            text = f"{sentences[0]}；{sentences[-1]}"
        return f"{chapter.get('title', chapter['chapter_id'])}: {text[:180]}"

    def _sentence_catalog(
        self,
        sentence_ids: Sequence[str],
        sentence_map: Dict[str, Dict[str, Any]],
    ) -> str:
        return "\n".join(
            f"[{sentence_id}] {sentence_map[sentence_id].get('text', '')}"
            for sentence_id in sentence_ids
            if sentence_id in sentence_map
        )

    def _fallback_world_state(
        self,
        blocks: Sequence[Dict[str, Any]],
        chapter_map: Dict[str, Dict[str, Any]],
        sketch_map: Dict[str, Dict[str, Any]],
        previous_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        chapter_ids = [chapter_id for block in blocks for chapter_id in block.get("owned_chapter_ids", [])]
        sketches = [sketch_map.get(chapter_id, {}) for chapter_id in chapter_ids]
        character_names = []
        organization_names = []
        for sketch in sketches:
            for name in sketch.get("characters", [])[:6]:
                if name not in character_names:
                    character_names.append(name)
            for name in sketch.get("organizations", [])[:6]:
                if name not in organization_names:
                    organization_names.append(name)
        snippets = [self._chapter_snippet(chapter_map[chapter_id]) for chapter_id in chapter_ids if chapter_id in chapter_map]
        world_state = {
            "active_characters": [{"name": name, "status": "active", "last_action": snippets[0][:50] if snippets else "本区间继续活跃"} for name in character_names[:6]],
            "active_organizations": [{"name": name, "status": "active", "key_change": "本区间继续活跃"} for name in organization_names[:6]],
            "key_relationships": [],
            "open_plot_threads": [sketch.get("tail_hook", "")[:40] for sketch in sketches if sketch.get("tail_hook")][:6],
            "recent_events_summary": "；".join(snippets[:3])[:150],
        }
        return self._merge_world_state(previous_state, world_state)

    def _fingerprint_line(self, sketch: Dict[str, Any]) -> str:
        title = sketch.get("title") or sketch.get("chapter_id", "未知章节")
        fingerprint = sketch.get("fingerprint") or "无"
        tail_hook = sketch.get("tail_hook") or "无"
        return f"{title}: {fingerprint} 尾钩: {tail_hook}"

    def _merge_world_state(
        self,
        previous_state: Dict[str, Any],
        new_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = self._empty_world_state()
        for field in WORLD_STATE_FIELDS:
            merged[field] = self._merge_field(field, previous_state.get(field), new_state.get(field))
        return merged

    def _merge_field(self, field: str, old_value: Any, new_value: Any) -> Any:
        if field == "recent_events_summary":
            return new_value or old_value or ""
        if not new_value:
            return list(old_value or [])
        return list(new_value)

    def _empty_world_state(self) -> Dict[str, Any]:
        return {
            "active_characters": [],
            "active_organizations": [],
            "key_relationships": [],
            "open_plot_threads": [],
            "recent_events_summary": "",
        }

    def _block_order(self, block_id: str) -> int:
        try:
            return int(block_id.rsplit("_", 1)[-1])
        except ValueError:
            return 0
