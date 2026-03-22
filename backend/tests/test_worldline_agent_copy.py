from app.services.worldline_agent_registry import WorldlineAgentRegistry


def test_worldline_agent_registry_uses_chinese_default_copy():
    registry = WorldlineAgentRegistry()
    branch = type(
        "Branch",
        (),
        {
            "actor_states": {
                "沈夜": {
                    "drive": "查明真相",
                    "tension": "身份随时暴露",
                }
            },
            "organization_states": {
                "玄霄宗": {
                    "drive": "维持宗门秩序",
                    "tension": "内部派系冲突升级",
                }
            },
            "relationship_states": [
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "change": "stable",
                }
            ],
        },
    )()

    agents = registry.list_agents(branch)

    character = next(item for item in agents if item["agent_kind"] == "character")
    organization = next(item for item in agents if item["agent_kind"] == "organization")
    relation = next(item for item in agents if item["agent_kind"] == "relationship")

    assert character["role"] == "角色"
    assert organization["role"] == "组织"
    assert relation["role"] == "关系推动者"
    assert "关系 agent" not in relation["summary"]
