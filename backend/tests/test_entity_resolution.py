from app.services.entity_resolution_service import EntityResolutionService


class StubLlmClient:
    def __init__(self, results):
        self.results = list(results)
        self.messages = []

    def chat_json_value(self, messages, temperature=0.1, max_tokens=256):
        self.messages.append(messages)
        return self.results.pop(0)


def test_entity_resolution_merges_known_aliases_without_llm():
    service = EntityResolutionService(llm_client=StubLlmClient([]))
    story_memory = {
        "entity_registry": {
            "沈夜": {
                "name": "沈夜",
                "entity_type": "character",
                "aliases": ["夜哥"],
                "mention_blocks": ["block_0001"],
                "summary": "主角",
                "evidence": ["沈夜现身"],
            },
            "夜哥": {
                "name": "夜哥",
                "entity_type": "character",
                "aliases": [],
                "mention_blocks": ["block_0002"],
                "summary": "别名写法",
                "evidence": ["夜哥出手"],
            },
        },
        "alias_map": {"夜哥": "沈夜"},
    }

    resolved = service.resolve(story_memory)

    assert "夜哥" not in resolved["entity_registry"]
    assert resolved["entity_registry"]["沈夜"]["mention_blocks"] == ["block_0001", "block_0002"]


def test_entity_resolution_asks_llm_for_similar_entities():
    client = StubLlmClient(
        [{"merge": True, "canonical_name": "秦昭", "reason": "同一角色的异写"}]
    )
    service = EntityResolutionService(llm_client=client)
    story_memory = {
        "entity_registry": {
            "秦昭": {
                "name": "秦昭",
                "entity_type": "character",
                "aliases": [],
                "mention_blocks": ["block_0001"],
                "summary": "沈夜盟友",
                "evidence": ["秦昭陪同调查"],
            },
            "秦照": {
                "name": "秦照",
                "entity_type": "character",
                "aliases": [],
                "mention_blocks": ["block_0002"],
                "summary": "与沈夜同行",
                "evidence": ["秦照再次现身"],
            },
        },
        "alias_map": {},
    }

    resolved = service.resolve(story_memory)

    assert "秦照" not in resolved["entity_registry"]
    assert "秦昭" in resolved["entity_registry"]
    assert "秦照再次现身" in client.messages[0][1]["content"]
