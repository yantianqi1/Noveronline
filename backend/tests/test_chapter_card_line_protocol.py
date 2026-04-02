from app.services.chapter_card_generator import ChapterCardGenerator


class ChapterCardLineClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del response_format
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "## 子任务\nsummary" in prompt:
            return (
                "SUMMARY|summary_text=宁毅在苏家逐步确认自己的新处境|start_anchor=宁毅从昏迷中醒来后开始观察周围变化|"
                "end_anchor=苏檀儿的出现让宁毅正式卷入苏家局势|timeline_note=时间线无明确推进|"
                "sentence_refs=chapter_0001_s001,chapter_0001_s003"
            )
        if "## 子任务\nevents_threads" in prompt:
            return (
                "EVENT|summary=宁毅醒来后确认自己身处陌生世界|sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
                "THREAD|thread_key=宁毅穿越之谜|summary=宁毅仍不清楚自己为何会来到苏家|sentence_refs=chapter_0001_s001,chapter_0001_s002"
            )
        return (
            "CHAR_STATE|name=宁毅|state=active|summary=开始观察并适应苏家环境|sentence_refs=chapter_0001_s001,chapter_0001_s002\n"
            "REL_STATE|source=宁毅|target=苏檀儿|state=co_occurrence|summary=两人在苏家首次公开同框|sentence_refs=chapter_0001_s003\n"
            "ENTITY|name=宁毅|entity_type=character\n"
            "ENTITY|name=苏檀儿|entity_type=character\n"
            "ENTITY|name=苏家|entity_type=organization"
        )


class LineRouter:
    def __init__(self):
        self.client = ChapterCardLineClient()

    def build_client(self, module_key):
        assert module_key == "novel_chapter_summarizer"
        return self.client


def test_chapter_card_generator_materializes_line_protocol():
    router = LineRouter()
    generator = ChapterCardGenerator(llm_router=router)

    payload = generator.generate_cards(
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "order": 1,
                "title": "风雪将起",
                "content": "宁毅从昏迷中醒来。小婵告诉他是苏家赘婿。苏檀儿回府后自然地挽住宁毅的手。",
                "sentence_ids": ["chapter_0001_s001", "chapter_0001_s002", "chapter_0001_s003"],
            }
        ],
        story_memory={"event_timeline": [], "open_threads": [], "world_rules": []},
        block_analyses={"blocks": [{"block_id": "block_0001", "plot_summary": "宁毅开始观察苏家局势。"}]},
        sentence_atlas=[
            {"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 1, "text": "宁毅从昏迷中醒来。", "char_range": {"start": 0, "end": 9}},
            {"sentence_id": "chapter_0001_s002", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 2, "text": "小婵告诉他是苏家赘婿。", "char_range": {"start": 9, "end": 21}},
            {"sentence_id": "chapter_0001_s003", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 3, "text": "苏檀儿回府后自然地挽住宁毅的手。", "char_range": {"start": 21, "end": 38}},
        ],
    )

    chapter = payload["chapters"][0]
    assert "[chapter_0001_s001]" in router.client.calls[0]
    assert chapter["summary_text"] == "宁毅在苏家逐步确认自己的新处境"
    assert chapter["summary_sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s003"]
    assert chapter["key_events"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert chapter["open_threads"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert chapter["character_state_updates"][0]["sentence_refs"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert chapter["relationship_updates"][0]["sentence_refs"] == ["chapter_0001_s003"]


def test_chapter_card_generator_retries_when_model_returns_invalid_sentence_refs():
    class FlakyLineClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
            del messages, temperature, max_tokens, response_format
            self.calls += 1
            if self.calls == 1:
                return "SUMMARY|summary_text=宁毅继续推进|start_anchor=承接前文|end_anchor=留下悬念|timeline_note=时间线无明确推进|sentence_refs=第二十六章 考校|第三十九章 一夜鱼龙舞（五）"
            if self.calls == 2:
                return "SUMMARY|summary_text=宁毅继续推进|start_anchor=承接前文|end_anchor=留下悬念|timeline_note=时间线无明确推进|sentence_refs=chapter_0001_s001"
            if self.calls == 3:
                return "EVENT|summary=宁毅继续推进当前行动|sentence_refs=chapter_0001_s001"
            return "CHAR_STATE|name=宁毅|state=active|summary=继续行动|sentence_refs=chapter_0001_s001\nENTITY|name=宁毅|entity_type=character"

    class RetryRouter:
        def __init__(self):
            self.client = FlakyLineClient()

        def build_client(self, module_key):
            return self.client

    router = RetryRouter()
    generator = ChapterCardGenerator(llm_router=router)

    payload = generator.generate_cards(
        chapters=[{"chapter_id": "chapter_0001", "order": 1, "title": "风雪将起", "content": "宁毅继续推进当前行动。", "sentence_ids": ["chapter_0001_s001"]}],
        story_memory={"event_timeline": [], "open_threads": [], "world_rules": []},
        block_analyses={"blocks": []},
        sentence_atlas=[{"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 1, "text": "宁毅继续推进当前行动。", "char_range": {"start": 0, "end": 10}}],
    )

    assert router.client.calls == 4
    assert payload["chapters"][0]["summary_sentence_refs"] == ["chapter_0001_s001"]
