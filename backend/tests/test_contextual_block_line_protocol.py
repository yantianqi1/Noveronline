import asyncio

from app.services.contextual_block_analyzer import ContextualBlockAnalyzer


class ContextLineProtocolClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del response_format
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "## 子任务\nplot_summary" in prompt:
            return "SUMMARY|text=宁毅在苏家逐步确认自己的新处境，并与苏檀儿建立公开联系|sentence_refs=chapter_0001_s001,chapter_0001_s003"
        if "## 子任务\nstate_updates" in prompt:
            return (
                "CHAR_STATE|name=宁毅|state=active|sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
                "REL_STATE|source=宁毅|target=苏檀儿|state=co_occurrence|sentence_refs=chapter_0001_s003\n"
                "END_STATE|focus_characters=宁毅,苏檀儿|focus_organizations=苏家|open_threads=宁毅穿越之谜|"
                "narrative_momentum=宁毅需要继续观察苏家的局势|summary=苏家内部关系开始把宁毅卷入更深的局面|"
                "sentence_refs=chapter_0001_s002,chapter_0001_s003"
            )
        return "THREAD_UPDATE|thread_key=宁毅穿越之谜|status=progressed|summary=宁毅已经确认自己成了苏家赘婿，但仍未知穿越原因|sentence_refs=chapter_0001_s001,chapter_0001_s002"


def test_contextual_block_analyzer_materializes_line_protocol():
    analyzer = ContextualBlockAnalyzer(llm_client=ContextLineProtocolClient())

    payload = asyncio.run(analyzer.analyze_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
                "owned_sentence_ids": ["chapter_0001_s001", "chapter_0001_s002", "chapter_0001_s003"],
                "context_sentence_ids": [],
            }
        ],
        local_block_facts=[
            {
                "block_id": "block_0001",
                "local_summary": "宁毅醒来后逐步确认自身处境，并与苏檀儿在苏家公开碰面",
                "local_summary_sentence_refs": ["chapter_0001_s001", "chapter_0001_s003"],
                "local_entities": [{"name": "宁毅", "entity_type": "character"}],
                "local_relationship_changes": [],
                "local_threads": [{"thread_key": "宁毅穿越之谜", "status": "open", "summary": "线索未结。"}],
                "local_events": [{"characters": ["宁毅"], "evidence": ["宁毅从昏迷中醒来。"], "sentence_refs": ["chapter_0001_s001"]}],
            }
        ],
        snapshots=[{"block_id": "block_0001", "recent_blocks": []}],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "title": "第1章",
                "content": "宁毅从昏迷中醒来。小婵告诉他是苏家赘婿。苏檀儿回府后自然地挽住宁毅的手。",
                "sentence_ids": ["chapter_0001_s001", "chapter_0001_s002", "chapter_0001_s003"],
            }
        ],
        use_llm=True,
        sentence_atlas=[
            {"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "order": 1, "chapter_order": 1, "text": "宁毅从昏迷中醒来。", "char_range": {"start": 0, "end": 9}},
            {"sentence_id": "chapter_0001_s002", "chapter_id": "chapter_0001", "order": 2, "chapter_order": 1, "text": "小婵告诉他是苏家赘婿。", "char_range": {"start": 9, "end": 21}},
            {"sentence_id": "chapter_0001_s003", "chapter_id": "chapter_0001", "order": 3, "chapter_order": 1, "text": "苏檀儿回府后自然地挽住宁毅的手。", "char_range": {"start": 21, "end": 38}},
        ],
    ))

    block = payload["blocks"][0]
    assert block["plot_summary_sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s003"]
    assert block["character_state_updates"][0]["evidence"] == ["宁毅从昏迷中醒来。", "小婵告诉他是苏家赘婿。"]
    assert block["relationship_updates"][0]["sentence_refs"] == ["chapter_0001_s003"]
    assert block["thread_updates"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert block["block_end_state"]["sentence_refs"] == ["chapter_0001_s002", "chapter_0001_s003"]
