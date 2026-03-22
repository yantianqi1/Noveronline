"""种子任务日志回调构造器。"""

from typing import Any, Dict

from .seed_task_progress import SeedTaskProgressTracker


def build_block_progress_callback(
    progress: SeedTaskProgressTracker,
    stage: str,
    title_prefix: str,
):
    def callback(event_type: str, block: Dict[str, Any]) -> None:
        meta = _block_meta(block)
        detail = _block_detail(block)
        if event_type == "start":
            progress.block_started(stage, f"开始{title_prefix} {block['block_id']}", detail, meta)
            return
        progress.block_completed(stage, f"完成{title_prefix} {block['block_id']}", detail, meta)

    return callback


def build_ontology_progress_callback(progress: SeedTaskProgressTracker):
    def callback(event_type: str, payload: Dict[str, Any]) -> None:
        if event_type == "offline":
            progress.llm_action("当前使用规则生成本体", "summary", "离线规则")
            return
        if event_type == "start":
            progress.llm_action("正在等待模型生成本体", "summary", f"上下文 {payload['summary_length']} 字")
            return
        progress.note(
            "ontology",
            "小说本体生成完成",
            f"实体类型 {payload['entity_type_count']} 个",
            meta={"kind": "artifact", "artifact": "ontology"},
        )

    return callback


def build_anchor_progress_callback(progress: SeedTaskProgressTracker):
    def callback(event_type: str, anchor: Dict[str, Any]) -> None:
        meta = {
            "kind": "anchor",
            "anchor_id": anchor.get("anchor_id", ""),
            "target_type": "anchor",
            "target_label": anchor.get("anchor_id", ""),
            "chapter_range": anchor.get("chapter_range"),
        }
        detail = _anchor_detail(anchor)
        if event_type == "start":
            progress.llm_action("正在生成剧情锚点", "anchor", anchor.get("anchor_id", ""), meta)
            return
        progress.note("anchor_generation", f"完成剧情锚点 {anchor.get('anchor_id', '')}", detail, meta=meta)

    return callback


def _block_meta(block: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "block",
        "block_id": block["block_id"],
        "target_type": "block",
        "target_label": block["block_id"],
        "chapter_range": block.get("owned_chapter_range"),
        "source_names": block.get("source_names", []),
    }


def _block_detail(block: Dict[str, Any]) -> str:
    chapter_range = block.get("owned_chapter_range") or {}
    start = chapter_range.get("start_order")
    end = chapter_range.get("end_order")
    if start and end:
        return f"当前块覆盖第 {start}-{end} 章"
    return "当前块已进入处理队列"


def _anchor_detail(anchor: Dict[str, Any]) -> str:
    chapter_range = anchor.get("chapter_range") or {}
    start = chapter_range.get("start")
    end = chapter_range.get("end")
    if start and end:
        return f"当前锚点覆盖第 {start}-{end} 章"
    return "当前锚点已进入处理队列"
