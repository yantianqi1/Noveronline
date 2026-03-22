from app.services.anchor_point_builder import AnchorPointBuilder


class CapturingLlmClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
        self.messages.append(messages)
        return self.payloads.pop(0)


def _blocks():
    return [
        {
            "block_id": "block_0001",
            "order": 1,
            "owned_chapter_ids": [f"chapter_{order:04d}" for order in range(1, 6)],
            "owned_chapter_range": {"start_order": 1, "end_order": 5},
        },
        {
            "block_id": "block_0002",
            "order": 2,
            "owned_chapter_ids": [f"chapter_{order:04d}" for order in range(6, 11)],
            "owned_chapter_range": {"start_order": 6, "end_order": 10},
        },
    ]


def _chapters():
    return [
        {
            "chapter_id": f"chapter_{order:04d}",
            "order": order,
            "title": f"第{order}章",
            "content": f"第{order}章里沈夜继续追查旧案。章末留下新的悬念。",
        }
        for order in range(1, 11)
    ]


def _skeleton():
    return {
        "global_characters": [{"name": "沈夜", "appearance_count": 10}],
        "chapter_sketches": [
            {
                "chapter_id": f"chapter_{order:04d}",
                "order": order,
                "fingerprint": f"第{order}章指纹：沈夜推进调查。",
                "tail_hook": f"第{order}章结尾钩子。",
            }
            for order in range(1, 11)
        ],
    }


def test_anchor_point_builder_builds_cumulative_anchor_snapshots():
    client = CapturingLlmClient(
        [
            {
                "world_state": {
                    "active_characters": [{"name": "沈夜", "status": "active"}],
                    "active_organizations": [],
                    "key_relationships": [],
                    "open_plot_threads": ["旧案真相"],
                    "recent_events_summary": "第1-5章：沈夜开始调查。",
                }
            },
            {
                "world_state": {
                    "active_characters": [{"name": "沈夜", "status": "injured"}],
                    "active_organizations": [],
                    "key_relationships": [],
                    "open_plot_threads": ["旧案真相", "镜湖异动"],
                    "recent_events_summary": "第6-10章：调查升级。",
                }
            },
        ]
    )
    builder = AnchorPointBuilder(llm_client=client)

    payload = builder.build(
        blocks=_blocks(),
        chapters=_chapters(),
        skeleton=_skeleton(),
        anchor_interval=1,
    )

    assert payload["anchor_count"] == 2
    assert payload["anchors"][0]["anchor_id"] == "anchor_0001"
    assert payload["anchors"][1]["world_state"]["active_characters"][0]["status"] == "injured"
    assert "旧案真相" in payload["anchors"][1]["world_state"]["open_plot_threads"]
    assert "前一个锚点的世界状态" in client.messages[1][1]["content"]
    assert "第6章指纹" in client.messages[1][1]["content"]


def test_anchor_point_builder_nearest_anchor_uses_latest_completed_anchor():
    builder = AnchorPointBuilder(llm_client=CapturingLlmClient([]))
    anchors = [
        {"anchor_id": "anchor_0001", "end_block_order": 1},
        {"anchor_id": "anchor_0002", "end_block_order": 3},
    ]

    assert builder.nearest_anchor("block_0001", anchors) is None
    assert builder.nearest_anchor("block_0002", anchors)["anchor_id"] == "anchor_0001"
    assert builder.nearest_anchor("block_0003", anchors)["anchor_id"] == "anchor_0001"
    assert builder.nearest_anchor("block_0004", anchors)["anchor_id"] == "anchor_0002"
