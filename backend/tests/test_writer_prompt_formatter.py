from app.services.writer_prompt_formatter import WriterPromptFormatter


def _item(category: str, summary: str, why: str, *, memory_layer: str = "canon"):
    return {
        "item_id": f"item_{category}_{summary}",
        "category": category,
        "summary": summary,
        "why_it_matters": why,
        "memory_layer": memory_layer,
    }


def test_writer_prompt_formatter_splits_sections_and_hides_candidates_by_default():
    formatter = WriterPromptFormatter()
    pack = {
        "context_scope": {
            "chapter_id": "chapter_0002",
            "pov_character": "沈夜",
            "writing_goal": "生成场景卡",
            "include_candidates": False,
        },
        "must_know": [
            _item("continuity", "秦昭带沈夜来到废塔前。", "必须承接本章起点。"),
            _item("world_rule", "镜湖引擎会记录识海残痕。", "不能违背世界规则。"),
        ],
        "should_know": [
            _item("relationship", "沈夜与秦昭暂时联手。", "人物关系会影响场景张力。"),
            _item("continuity_bridge", "顾行舟可能提前封锁镜湖谷。", "需要维持章节衔接。"),
            _item("open_thread", "镜湖真相仍未查清。", "需要持续推进线索。"),
            _item("runtime_memory", "沈夜想先试探顾行舟底牌。", "当前策略会影响动作。"),
            _item("runtime_memory", "沈夜怀疑顾行舟已拿到密信原件。", "候选推演，不是 canon。", memory_layer="candidate"),
        ],
        "warnings": [_item("consistency_risk", "夜哥称呼存在歧义。", "写作时需要消歧。")],
        "scene_candidates": [
            {
                "title": "废塔试探",
                "setup": "沈夜与秦昭进入废塔。",
                "tension": "残响提前暴露顾行舟布置。",
                "why_now": "当前线索正指向镜湖谷。",
                "depends_on": ["chapter_0002"],
            }
        ],
    }

    prompt = formatter.format(pack)

    assert "## 写作目标" in prompt
    assert "## 必须延续的事实" in prompt
    assert "## 当前人物与关系" in prompt
    assert "## 开放线索与连续性" in prompt
    assert "## 风险提示" in prompt
    assert "## 候选场景" in prompt
    assert "## 可参考候选设定" in prompt
    assert "沈夜与秦昭暂时联手。" in prompt
    assert "镜湖真相仍未查清。" in prompt
    assert "候选推演，不是 canon。" not in prompt
    assert "默认不注入 candidate 设定" in prompt


def test_writer_prompt_formatter_shows_candidates_only_in_candidate_section():
    formatter = WriterPromptFormatter()
    pack = {
        "context_scope": {
            "branch_id": "main",
            "pov_character": "沈夜",
            "writing_goal": "生成 worldline 场景卡",
            "include_candidates": True,
        },
        "must_know": [],
        "should_know": [
            _item("relationship", "沈夜与秦昭的关系开始失衡。", "关系会影响对话。"),
            _item("runtime_memory", "沈夜准备公开密信残页。", "候选推演，不是 canon。", memory_layer="candidate"),
        ],
        "warnings": [],
        "scene_candidates": [],
    }

    prompt = formatter.format(pack)

    relationship_section = prompt.split("## 当前人物与关系", 1)[1].split("## 开放线索与连续性", 1)[0]
    candidate_section = prompt.split("## 可参考候选设定", 1)[1]

    assert "沈夜与秦昭的关系开始失衡。" in relationship_section
    assert "沈夜准备公开密信残页。" not in relationship_section
    assert "沈夜准备公开密信残页。" in candidate_section
    assert "非 canon" in candidate_section
