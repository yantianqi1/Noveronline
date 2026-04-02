from app.services.entity_resolution_service import EntityResolutionService
from app.services.story_ontology_generator import StoryOntologyGenerator


class OntologyLineClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del response_format
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "## 子任务\nentity_types" in prompt:
            return (
                "ENTITY_TYPE|name=Character|description=故事中的命名角色|attributes=importance_tier:text:角色重要性,identity_hint:text:角色身份线索|examples=宁毅,苏檀儿\n"
                "ENTITY_TYPE|name=Organization|description=故事中的组织势力|attributes=organization_type:text:组织类型,public_goal:text:组织公开目标|examples=苏家,乌家"
            )
        return (
            "EDGE_TYPE|name=BELONGS_TO|description=角色对组织的从属关系|source_targets=Character>Organization|attributes=loyalty_level:text:忠诚度\n"
            "SUMMARY|text=当前故事围绕宁毅进入苏家后的身份适应与家族格局展开\n"
            "FOCUS|text=宁毅在苏家的身份变化\n"
            "FOCUS|text=苏家内部权力关系"
        )


class EntityDecisionClient:
    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        del temperature, max_tokens, response_format
        return "DECISION|merge=true|canonical_name=秦昭|confidence=0.92|reason=秦照是秦昭的异写"


def test_story_ontology_generator_materializes_line_protocol():
    generator = StoryOntologyGenerator(llm_client=OntologyLineClient())

    payload = generator.generate(
        document_texts=["第1章\n宁毅进入苏家之后开始适应新的身份。"],
        analysis_goal="观察角色与组织关系",
        use_llm=True,
    )

    assert payload["entity_types"][0]["name"] == "Character"
    assert payload["edge_types"][0]["name"] == "BELONGS_TO"
    assert payload["analysis_summary"]
    assert payload["story_focus"] == ["宁毅在苏家的身份变化", "苏家内部权力关系"]


def test_entity_resolution_service_accepts_line_protocol_decision():
    service = EntityResolutionService(llm_client=EntityDecisionClient())
    story_memory = {
        "entity_registry": {
            "秦昭": {"name": "秦昭", "entity_type": "character", "aliases": [], "mention_blocks": ["block_0001"], "summary": "沈夜盟友", "evidence": ["秦昭陪同调查"]},
            "秦照": {"name": "秦照", "entity_type": "character", "aliases": [], "mention_blocks": ["block_0002"], "summary": "与沈夜同行", "evidence": ["秦照再次现身"]},
        },
        "alias_map": {},
    }

    resolved = service.resolve(story_memory)

    assert "秦照" not in resolved["entity_registry"]
    assert resolved["alias_map"]["秦照"] == "秦昭"
