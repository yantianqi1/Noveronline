import asyncio

from app.services.local_block_fact_extractor import LocalBlockFactExtractor


class LineProtocolClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del response_format
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "## 子任务\nevents" in prompt:
            return (
                "EVENT|summary=宁毅从昏迷中醒来，确认自己来到陌生世界|characters=宁毅|organizations=|"
                "sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
                "EVENT|summary=苏檀儿回府后与宁毅第一次公开同框|characters=宁毅,苏檀儿|organizations=苏家|"
                "sentence_refs=chapter_0001_s003"
            )
        if "## 子任务\nentities" in prompt:
            return (
                "ENTITY|name=宁毅|entity_type=character|aliases=姑爷,立恒|summary=从陌生环境中迅速恢复判断|"
                "importance_tier=protagonist|sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
                "ENTITY|name=苏檀儿|entity_type=character|aliases=小姐,娘子|summary=回府后主动稳住场面|"
                "importance_tier=major|sentence_refs=chapter_0001_s003\n"
                "ENTITY|name=苏家|entity_type=organization|aliases=|summary=宁毅当前寄身的富商家族|"
                "importance_tier=major|sentence_refs=chapter_0001_s002,chapter_0001_s003"
            )
        if "## 子任务\nrelationships" in prompt:
            return (
                "REL|source=宁毅|target=苏檀儿|change=co_occurrence|weight=1|"
                "sentence_refs=chapter_0001_s003"
            )
        return (
            "THREAD|thread_key=宁毅穿越之谜|status=open|summary=宁毅仍未弄清自己为何来到这个世界|"
            "sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
            "SUMMARY|text=宁毅醒来后逐步确认自身处境，并与苏檀儿在苏家公开碰面|"
            "sentence_refs=chapter_0001_s001,chapter_0001_s003"
        )


def test_local_block_fact_extractor_materializes_line_protocol_into_packet():
    client = LineProtocolClient()
    extractor = LocalBlockFactExtractor(llm_client=client)

    payload = asyncio.run(extractor.extract_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
                "owned_sentence_ids": ["chapter_0001_s001", "chapter_0001_s002", "chapter_0001_s003"],
                "context_sentence_ids": [],
                "owned_chapter_range": {"start_order": 1, "end_order": 1},
                "order": 1,
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "title": "第1章",
                "content": "宁毅从昏迷中醒来。小婵告诉他是苏家赘婿。苏檀儿回府后自然地挽住宁毅的手。",
                "sentence_ids": ["chapter_0001_s001", "chapter_0001_s002", "chapter_0001_s003"],
            }
        ],
        use_llm=True,
        skeleton={"global_characters": [], "global_organizations": [], "chapter_sketches": []},
        anchors={"anchors": []},
        sentence_atlas=[
            {"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "order": 1, "chapter_order": 1, "text": "宁毅从昏迷中醒来。", "char_range": {"start": 0, "end": 9}},
            {"sentence_id": "chapter_0001_s002", "chapter_id": "chapter_0001", "order": 2, "chapter_order": 1, "text": "小婵告诉他是苏家赘婿。", "char_range": {"start": 9, "end": 21}},
            {"sentence_id": "chapter_0001_s003", "chapter_id": "chapter_0001", "order": 3, "chapter_order": 1, "text": "苏檀儿回府后自然地挽住宁毅的手。", "char_range": {"start": 21, "end": 38}},
        ],
    ))

    packet = payload["packets"][0]
    assert len(client.calls) == 4
    assert packet["local_events"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert packet["local_events"][0]["evidence"] == ["宁毅从昏迷中醒来。", "小婵告诉他是苏家赘婿。"]
    assert packet["local_entities"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert packet["local_relationship_changes"][0]["evidence"] == ["苏檀儿回府后自然地挽住宁毅的手。"]
    assert packet["local_threads"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert packet["local_summary"] == "宁毅醒来后逐步确认自身处境，并与苏檀儿在苏家公开碰面"
    assert packet["local_summary_sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s003"]
