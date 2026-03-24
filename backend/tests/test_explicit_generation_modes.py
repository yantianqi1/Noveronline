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


def test_narrative_archivist_maps_character_detail_fields_into_template_payload():
    archivist = NarrativeEntityArchivist(
        llm_client=StubJsonValueClient(
            [{
                "importance_tier": "protagonist",
                "entity_role": "主角",
                "core_drive": "查清父亲死因并公开镜湖真相",
                "surface_mask": "冷静寡言，表面顺从局势",
                "hidden_tension": "既要利用宗门资源，又无法信任宗门",
                "relationship_summary": "与秦昭互相利用，与玄霄宗高度对立",
                "agent_behavior_hint": "会先暗查证据，再选择公开施压",
                "human_ai_relation_tag": "human",
                "notable_risks": ["身份暴露", "证据被提前销毁"],
                "personality": "多疑克制，但在关键时刻会孤注一掷",
                "skills": ["潜入", "审讯取证"],
                "loyalty": "优先忠于父亲留下的真相线索，其次才是盟友",
                "secrets": ["掌握镜湖铜片的真实用途"],
                "long_term_goal": "摧毁掩盖实验真相的权力结构",
                "short_term_goal": "在试炼前确认密信与铜片能否互证",
            }]
        )
    )
    entity = EntityNode(
        uuid="char_1",
        name="沈夜",
        labels=["Entity", "Character"],
        summary="主角，正在追查父亲死因。",
        attributes={"importance_tier": "protagonist", "identity_hint": "外门弟子"},
    )

    archive = archivist.generate_archive(entity)

    assert archive.template_payload["behavior"]["skills"] == ["潜入", "审讯取证"]
    assert archive.template_payload["behavior"]["loyalty"] == "优先忠于父亲留下的真相线索，其次才是盟友"
    assert archive.template_payload["behavior"]["long_term_goal"] == "摧毁掩盖实验真相的权力结构"
    assert archive.template_payload["behavior"]["short_term_goal"] == "在试炼前确认密信与铜片能否互证"
    assert archive.template_payload["private"]["secrets"] == ["掌握镜湖铜片的真实用途"]
    assert archive.template_payload["identity"]["identity_hint"] == "外门弟子"


def test_narrative_archivist_maps_organization_detail_fields_into_template_payload():
    archivist = NarrativeEntityArchivist(
        llm_client=StubJsonValueClient(
            [{
                "importance_tier": "major",
                "entity_role": "宗门统治者",
                "core_drive": "维持镜湖体系与宗门统治合法性",
                "surface_mask": "对外宣称维持试炼秩序",
                "hidden_tension": "既要掩盖旧实验，又担心白泽司反噬",
                "relationship_summary": "对沈夜实施压制，对白泽司保持脆弱合作",
                "agent_behavior_hint": "会优先控制信息流并分化反对者",
                "human_ai_relation_tag": "none",
                "notable_risks": ["密库曝光", "内部派系分裂"],
                "resources": ["刑堂", "试炼阵", "镜湖密库"],
                "internal_factions": ["顾行舟一系", "林雁回一系"],
                "territorial_control": "玄霄山门、镜湖谷与外门试炼区域",
                "public_stance": "一切以宗门秩序与弟子安全为先",
                "strategic_goal": "在白泽司与回声会之间维持主动权",
                "conflict_targets": ["沈夜", "回声会"],
            }]
        )
    )
    entity = EntityNode(
        uuid="org_1",
        name="玄霄宗",
        labels=["Entity", "Organization"],
        summary="掌控试炼与秩序的宗门。",
        attributes={"importance_tier": "major", "organization_type": "sect"},
    )

    archive = archivist.generate_archive(entity)

    assert archive.template_payload["behavior"]["resources"] == ["刑堂", "试炼阵", "镜湖密库"]
    assert archive.template_payload["behavior"]["internal_factions"] == ["顾行舟一系", "林雁回一系"]
    assert archive.template_payload["behavior"]["public_stance"] == "一切以宗门秩序与弟子安全为先"
    assert archive.template_payload["behavior"]["strategic_goal"] == "在白泽司与回声会之间维持主动权"
    assert archive.template_payload["behavior"]["conflict_targets"] == ["沈夜", "回声会"]
    assert archive.template_payload["private"]["territorial_control"] == "玄霄山门、镜湖谷与外门试炼区域"
    assert archive.template_payload["identity"]["organization_type"] == "sect"


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
