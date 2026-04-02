from app.services.agents.registry import AgentTemplateRegistry


def test_agent_template_registry_returns_kind_and_tier_specific_sections():
    registry = AgentTemplateRegistry()

    protagonist_character = registry.describe("character", "protagonist")
    supporting_relationship = registry.describe("relationship", "supporting")
    generic_minor = registry.describe("location", "minor")

    assert protagonist_character["template_key"] == "character.protagonist.v1"
    assert "private" in protagonist_character["template_sections"]
    assert "skills" in protagonist_character["type_fields"]

    assert supporting_relationship["template_key"] == "relationship.supporting.v1"
    assert supporting_relationship["template_sections"] == [
        "identity",
        "motivation",
        "tension",
        "relationship",
        "state",
    ]
    assert "history" in supporting_relationship["type_fields"]

    assert generic_minor["template_key"] == "generic.minor.v1"
    assert generic_minor["template_sections"] == ["identity", "state", "summary"]
    assert generic_minor["type_fields"] == []
