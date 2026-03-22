from app.services.novel_seed_analyzer import NovelSeedAnalyzer


def test_seed_analyzer_filters_false_organization_candidates():
    text = "不一会，宁毅朝苏檀儿看去，密侦司的人已经赶到右相府。"

    analysis = NovelSeedAnalyzer().analyze_text(text)
    names = {item["name"] for item in analysis["organizations"]}

    assert "密侦司" in names
    assert "右相府" in names
    assert "不一会" not in names
    assert "宁毅朝" not in names
