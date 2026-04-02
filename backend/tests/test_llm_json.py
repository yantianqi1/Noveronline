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
