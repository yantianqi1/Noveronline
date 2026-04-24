import pytest

from app.utils.llm_json import parse_json_response


def test_parse_json_response_repairs_missing_array_closer_before_next_object():
    response = (
        '{"local_entities":['
        '{"name":"苏檀儿","evidence":["小姐听说姑爷很喜欢下棋，特意买回来送给姑爷的。"},'
        '{"name":"小婵","evidence":["姑爷赢了？"]}'
        '],"local_summary":"宁毅逐渐融入苏家"}'
    )

    payload = parse_json_response(response)

    assert payload["local_entities"][0]["name"] == "苏檀儿"
    assert payload["local_entities"][0]["evidence"] == ["小姐听说姑爷很喜欢下棋，特意买回来送给姑爷的。"]
    assert payload["local_entities"][1]["name"] == "小婵"


def test_parse_json_response_repairs_raw_newlines_inside_strings():
    response = '{"local_summary":"第一行\n第二行","local_events":[]}'

    payload = parse_json_response(response)

    assert payload["local_summary"] == "第一行 第二行"
    assert payload["local_events"] == []


def test_parse_json_response_still_raises_on_non_json_text():
    with pytest.raises(ValueError, match="LLM返回的JSON格式无效"):
        parse_json_response("这不是 JSON")


# ── 截断修复测试 ──


def test_parse_truncated_json_missing_closing_braces():
    """finish_reason='length' 导致 JSON 被截断，缺少闭合括号。"""
    response = '{"characters": [{"name": "宁毅"}, {"name": "苏檀儿"}'
    payload = parse_json_response(response, truncated=True)
    assert payload["characters"][0]["name"] == "宁毅"
    assert payload["characters"][1]["name"] == "苏檀儿"


def test_parse_truncated_json_mid_string():
    """截断发生在字符串值中间。"""
    response = '{"summary": "宁毅初入苏家，众人对他的态度各'
    payload = parse_json_response(response, truncated=True)
    assert "宁毅" in payload["summary"]


def test_parse_truncated_json_trailing_incomplete_key():
    """截断时留下不完整的 key-value 对。"""
    response = '{"name": "宁毅", "desc": '
    payload = parse_json_response(response, truncated=True)
    assert payload["name"] == "宁毅"


# ── 正则提取测试 ──


def test_parse_json_embedded_in_explanation():
    """LLM 在 JSON 前后添加了解释文字，clean 无法处理的情况。"""
    response = (
        "好的，以下是分析结果：\n\n"
        '{"characters": ["宁毅", "苏檀儿"]}\n\n'
        "以上就是角色列表。"
    )
    payload = parse_json_response(response)
    assert payload["characters"] == ["宁毅", "苏檀儿"]


def test_parse_json_with_control_characters_in_values():
    """字符串值中包含控制字符（\x00-\x1f 范围）。"""
    response = '{"name": "宁\x02毅", "role": "主\x1f角"}'
    payload = parse_json_response(response)
    assert "宁" in payload["name"]
    assert "毅" in payload["name"]


def test_parse_json_with_newlines_in_string_values_via_regex():
    """字符串值内包含实际换行符，通过正则提取修复。"""
    # JSON 嵌在解释文字中，且字符串内有换行
    response = (
        "结果如下：\n"
        '{"bio": "宁毅是\n一个穿越者", "role": "主角"}\n'
        "分析完毕。"
    )
    payload = parse_json_response(response)
    assert "宁毅" in payload["bio"]
    assert payload["role"] == "主角"


# ── truncated=False 不影响现有行为 ──


def test_parse_json_truncated_false_still_raises_on_bad_input():
    """truncated=False 时，严重损坏的输入仍应抛出 ValueError。"""
    with pytest.raises(ValueError, match="LLM返回的JSON格式无效"):
        parse_json_response("完全不是 JSON 的内容，也没有大括号", truncated=False)


# ── Phase E-1: dropped-field warning ──


def test_repair_truncated_json_logs_dropped_field_name(monkeypatch):
    """When the trailing key:value pair is dropped, log the field name."""
    from app.utils import llm_json as llm_json_mod

    captured: list[tuple] = []

    def _fake_warning(*args, **kwargs):
        captured.append(args)

    monkeypatch.setattr(llm_json_mod.logger, "warning", _fake_warning)
    truncated = '{"summary": "hello", "world_building": '
    repaired = llm_json_mod._repair_truncated_json(truncated)
    assert repaired.endswith("}")
    flattened = " ".join(str(arg) for tup in captured for arg in tup)
    assert "world_building" in flattened
