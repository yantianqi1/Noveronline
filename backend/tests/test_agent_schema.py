from app.services.agents.registry import AgentSchemaRegistry
from app.services.agents.worldline import WorldlineAgentRegistry


def test_agent_schema_registry_merges_defaults_and_validates_required_fields():
    registry = AgentSchemaRegistry()
    registry.register_schema(
        "character",
        {
            "cultivation_stage": {
                "type": "str",
                "label": "境界",
                "required": False,
            }
        },
    )

    schema = registry.get_schema("character")
    errors = registry.validate_state(
        "character",
        {
            "drive": "查真相",
            "tension": "身份暴露",
            "role": "主角",
            "status": "active",
            "cultivation_stage": "筑基",
        },
    )
    missing_errors = registry.validate_state("character", {"status": "active"})

    assert "drive" in schema
    assert "personality" in schema
    assert "cultivation_stage" in schema
    assert errors == []
    assert any("drive" in item for item in missing_errors)


def test_worldline_agent_registry_exposes_kind_specific_schema():
    registry = WorldlineAgentRegistry()
    branch = type(
        "Branch",
        (),
        {
            "actor_states": {
                "沈夜": {
                    "drive": "查明真相",
                    "tension": "身份暴露",
                    "role": "主角",
                    "status": "active",
                }
            },
            "organization_states": {
                "玄霄宗": {
                    "drive": "维持秩序",
                    "tension": "派系对立",
                    "role": "宗门",
                    "status": "active",
                }
            },
            "relationship_states": [
                {"source": "沈夜", "target": "玄霄宗", "change": "stable"}
            ],
        },
    )()

    agents = registry.list_agents(branch)

    character = next(item for item in agents if item["agent_kind"] == "character")
    organization = next(item for item in agents if item["agent_kind"] == "organization")
    relation = next(item for item in agents if item["agent_kind"] == "relationship")

    assert "personality" in character["schema"]
    assert "territorial_control" in organization["schema"]
    assert "power_dynamic" in relation["schema"]
