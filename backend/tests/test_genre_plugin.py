from app.services.agents.registry import AgentSchemaRegistry
from app.services.genre_plugin import resolve_genre_plugin
from app.services.novel_seed_analyzer import NovelSeedAnalyzer


def test_wuxia_genre_plugin_extends_organization_suffix_and_relation_keywords():
    default_analysis = NovelSeedAnalyzer().analyze_text("沈夜与秦昭在落星山庄门前结拜。")
    wuxia_analysis = NovelSeedAnalyzer(genre="wuxia").analyze_text("沈夜与秦昭在落星山庄门前结拜。")

    default_org_names = {item["name"] for item in default_analysis["organizations"]}
    wuxia_org_names = {item["name"] for item in wuxia_analysis["organizations"]}
    relation_types = {item["relation_type"] for item in wuxia_analysis["relations"]}

    assert "落星山庄" not in default_org_names
    assert "落星山庄" in wuxia_org_names
    assert "ally" in relation_types


def test_xianxia_plugin_customizes_character_schema():
    plugin = resolve_genre_plugin("xianxia")
    registry = AgentSchemaRegistry()

    plugin.customize_agent_schema(registry)
    schema = registry.get_schema("character")

    assert "cultivation_stage" in schema
    assert "dao_heart" in schema
