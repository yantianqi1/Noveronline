import pytest

from app.services.narrative_entity_archivist import NarrativeEntityArchivist
from app.services.parallel_world_config_generator import ParallelWorldConfigGenerator
from app.services.story_ontology_generator import StoryOntologyGenerator
from app.services.zep_entity_reader import EntityNode


class StubJsonValueClient:
    def __init__(self, payload):
        self.payload = payload

    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        return self.payload


def test_story_ontology_requires_explicit_offline_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path / "uploads"))
    generator = StoryOntologyGenerator()

    with pytest.raises(ValueError, match="use_llm=False"):
        generator.generate(["沈夜与玄霄宗冲突升级。"], "分析世界观与角色关系")


def test_story_ontology_supports_explicit_offline_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path / "uploads"))
    generator = StoryOntologyGenerator()

    result = generator.generate(
        ["沈夜与玄霄宗冲突升级，镜湖引擎开始影响修士识海。"],
        "分析世界观与角色关系",
        use_llm=False,
    )

    assert result["entity_types"]
    assert result["edge_types"]
    assert result["story_focus"]


def test_story_ontology_accepts_single_object_list_payload():
    generator = StoryOntologyGenerator(
        llm_client=StubJsonValueClient(
            [{
                "entity_types": [{"name": "Character", "description": "Named story character", "attributes": [], "examples": ["沈夜"]}],
                "edge_types": [{"name": "KNOWS", "description": "Characters know each other", "source_targets": [], "attributes": []}],
                "analysis_summary": "镜湖主轴清晰。",
                "story_focus": ["镜湖真相"],
            }]
        )
    )

    result = generator.generate(["沈夜追查镜湖真相。"], "分析世界观与角色关系")

    assert result["entity_types"][0]["name"] == "Character"
    assert result["story_focus"] == ["镜湖真相"]


def test_story_ontology_rejects_multi_item_list_payload():
    generator = StoryOntologyGenerator(
        llm_client=StubJsonValueClient([{"entity_types": []}, {"entity_types": []}])
    )

    with pytest.raises(ValueError, match="小说本体生成必须返回单个 JSON 对象.*2 个元素的 list"):
        generator.generate(["沈夜追查镜湖真相。"], "分析世界观与角色关系")


def test_parallel_world_config_requires_explicit_offline_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path / "uploads"))
    generator = ParallelWorldConfigGenerator()

    with pytest.raises(ValueError, match="use_llm=False"):
        generator.generate("观察变量扰动", entities=[])


def test_parallel_world_config_supports_explicit_offline_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path / "uploads"))
    generator = ParallelWorldConfigGenerator()

    result = generator.generate(
        "观察变量扰动",
        entities=[],
        variables=["主角提前公开密信"],
        branch_count=2,
        use_llm=False,
    )

    assert result.simulation_goal == "观察变量扰动"
    assert len(result.branch_hypotheses) == 2


def test_parallel_world_config_accepts_single_object_list_payload():
    generator = ParallelWorldConfigGenerator(
        llm_client=StubJsonValueClient(
            [{
                "simulation_goal": "观察变量扰动",
                "world_variables": [{"name": "密信提前曝光", "description": "第一卷提前公开密信", "impact_axis": "主线推进"}],
                "branch_hypotheses": [{
                    "branch_id": "branch_1",
                    "title": "密信公开线",
                    "core_change": "密信提早公开",
                    "key_agents": ["沈夜"],
                    "expected_conflicts": ["玄霄宗反击"],
                    "narrative_value": "加速主线冲突",
                }],
                "timeline_focus": ["起因暴露"],
                "agent_behavior_axes": ["角色目标"],
            }]
        )
    )

    result = generator.generate("观察变量扰动", entities=[])

    assert result.simulation_goal == "观察变量扰动"
    assert result.world_variables[0].name == "密信提前曝光"


def test_parallel_world_config_rejects_multi_item_list_payload():
    generator = ParallelWorldConfigGenerator(
        llm_client=StubJsonValueClient([{"world_variables": []}, {"world_variables": []}])
    )

    with pytest.raises(ValueError, match="平行世界配置生成必须返回单个 JSON 对象.*2 个元素的 list"):
        generator.generate("观察变量扰动", entities=[])


def test_narrative_archivist_requires_explicit_offline_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path / "uploads"))
    archivist = NarrativeEntityArchivist()
    entity = EntityNode(
        uuid="char_1",
        name="沈夜",
        labels=["Entity", "Character"],
        summary="主角，正在追查父亲死因。",
        attributes={"importance_tier": "protagonist"},
    )

    with pytest.raises(ValueError, match="use_llm=False"):
        archivist.generate_archive(entity, use_llm=True)


def test_narrative_archivist_accepts_single_object_list_payload():
    archivist = NarrativeEntityArchivist(
        llm_client=StubJsonValueClient(
            [{
                "importance_tier": "major",
                "entity_role": "主角",
                "core_drive": "追查父亲死因",
                "surface_mask": "沉默隐忍",
                "hidden_tension": "不信任玄霄宗",
                "relationship_summary": "与秦昭结盟",
                "agent_behavior_hint": "会主动追索线索",
                "human_ai_relation_tag": "human",
                "notable_risks": ["线索暴露"],
            }]
        )
    )
    entity = EntityNode(
        uuid="char_1",
        name="沈夜",
        labels=["Entity", "Character"],
        summary="主角，正在追查父亲死因。",
        attributes={"importance_tier": "protagonist"},
    )

    archive = archivist.generate_archive(entity)

    assert archive.importance_tier == "major"
    assert archive.entity_role == "主角"


def test_narrative_archivist_rejects_multi_item_list_payload():
    archivist = NarrativeEntityArchivist(
        llm_client=StubJsonValueClient([{"importance_tier": "major"}, {"importance_tier": "minor"}])
    )
    entity = EntityNode(
        uuid="char_1",
        name="沈夜",
        labels=["Entity", "Character"],
        summary="主角，正在追查父亲死因。",
        attributes={"importance_tier": "protagonist"},
    )

    with pytest.raises(ValueError, match="叙事实体档案生成必须返回单个 JSON 对象.*2 个元素的 list"):
        archivist.generate_archive(entity)
