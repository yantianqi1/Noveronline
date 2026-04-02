from app.services.anchor_point_builder import AnchorPointBuilder


class AnchorLineClient:
    def __init__(self):
        self.messages = []

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del temperature, max_tokens, response_format
        self.messages.append(messages)
        return (
            "ACTIVE_CHARACTER|name=沈夜|status=active|last_action=继续追查镜湖旧案|sentence_refs=chapter_0001_s001\n"
            "ACTIVE_ORG|name=玄霄宗|status=震荡|key_change=镜湖旧案持续施压|sentence_refs=chapter_0001_s001\n"
            "KEY_REL|source=沈夜|target=玄霄宗|state=conflict|since_chapter=1|sentence_refs=chapter_0001_s001\n"
            "OPEN_THREAD|text=镜湖旧案真相仍未明朗|sentence_refs=chapter_0001_s001\n"
            "RECENT_EVENTS|text=沈夜推进了对镜湖旧案的追查|sentence_refs=chapter_0001_s001"
        )


def test_anchor_point_builder_materializes_line_protocol():
    client = AnchorLineClient()
    builder = AnchorPointBuilder(llm_client=client)

    payload = builder.build(
        blocks=[
            {
                "block_id": "block_0001",
                "order": 1,
                "owned_chapter_ids": ["chapter_0001"],
                "owned_chapter_range": {"start_order": 1, "end_order": 1},
                "owned_sentence_ids": ["chapter_0001_s001"],
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "order": 1,
                "title": "第1章",
                "content": "沈夜继续追查镜湖旧案。",
                "sentence_ids": ["chapter_0001_s001"],
            }
        ],
        skeleton={
            "global_characters": [{"name": "沈夜", "appearance_count": 1}],
            "chapter_sketches": [
                {
                    "chapter_id": "chapter_0001",
                    "order": 1,
                    "characters": ["沈夜"],
                    "organizations": ["玄霄宗"],
                    "fingerprint": "沈夜推进调查。",
                    "tail_hook": "镜湖旧案仍未结束。",
                }
            ],
        },
        sentence_atlas=[
            {"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 1, "text": "沈夜继续追查镜湖旧案。", "char_range": {"start": 0, "end": 12}},
        ],
        anchor_interval=1,
    )

    anchor = payload["anchors"][0]
    assert "[chapter_0001_s001]" in client.messages[0][1]["content"]
    assert anchor["world_state"]["active_characters"][0]["sentence_refs"] == ["chapter_0001_s001"]
    assert anchor["world_state"]["active_organizations"][0]["sentence_refs"] == ["chapter_0001_s001"]
    assert anchor["world_state"]["key_relationships"][0]["sentence_refs"] == ["chapter_0001_s001"]
    assert anchor["world_state"]["open_plot_threads"] == ["镜湖旧案真相仍未明朗"]
    assert anchor["world_state"]["recent_events_summary"] == "沈夜推进了对镜湖旧案的追查"


def test_anchor_point_builder_retries_when_model_returns_invalid_sentence_refs():
    class FlakyAnchorClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
            del messages, temperature, max_tokens, response_format
            self.calls += 1
            if self.calls == 1:
                return "ACTIVE_CHARACTER|name=宁毅|status=active|last_action=继续推进|sentence_refs=第二十二章 秋末冬初（下）|第二十六章 考校"
            return (
                "ACTIVE_CHARACTER|name=宁毅|status=active|last_action=继续推进|sentence_refs=chapter_0001_s001\n"
                "RECENT_EVENTS|text=宁毅继续推进当前行动|sentence_refs=chapter_0001_s001"
            )

    client = FlakyAnchorClient()
    builder = AnchorPointBuilder(llm_client=client)

    payload = builder.build(
        blocks=[{"block_id": "block_0001", "order": 1, "owned_chapter_ids": ["chapter_0001"], "owned_sentence_ids": ["chapter_0001_s001"], "owned_chapter_range": {"start_order": 1, "end_order": 1}}],
        chapters=[{"chapter_id": "chapter_0001", "order": 1, "title": "第1章", "content": "宁毅继续推进当前行动。", "sentence_ids": ["chapter_0001_s001"]}],
        skeleton={"global_characters": [], "global_organizations": [], "chapter_sketches": [{"chapter_id": "chapter_0001", "order": 1, "characters": ["宁毅"], "organizations": [], "fingerprint": "宁毅推进行动。", "tail_hook": "行动继续。"}]},
        sentence_atlas=[{"sentence_id": "chapter_0001_s001", "chapter_id": "chapter_0001", "chapter_order": 1, "order": 1, "text": "宁毅继续推进当前行动。", "char_range": {"start": 0, "end": 10}}],
        anchor_interval=1,
    )

    assert client.calls == 2
    assert payload["anchors"][0]["world_state"]["active_characters"][0]["sentence_refs"] == ["chapter_0001_s001"]
