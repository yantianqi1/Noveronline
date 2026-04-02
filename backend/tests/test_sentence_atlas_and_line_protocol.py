import pytest

from app.services.novel_chapter_segmenter import NovelChapterSegmenter
from app.services.seed_line_protocol import (
    LineProtocolError,
    parse_kv_line,
    parse_sentence_ref_list,
)


def test_novel_chapter_segmenter_builds_stable_sentence_atlas():
    segmenter = NovelChapterSegmenter()

    payload = segmenter.segment_documents(
        [
            {
                "source_name": "demo.txt",
                "text": "第1章 起疑\n沈夜收到密信。秦昭提醒他危险将近！\n\n第2章 废塔\n顾行舟已经提前布下埋伏？",
            }
        ]
    )

    chapters = payload["chapters"]
    atlas = payload["sentence_atlas"]

    assert [item["chapter_id"] for item in chapters] == ["chapter_0001", "chapter_0002"]
    assert chapters[0]["sentence_ids"] == ["chapter_0001_s001", "chapter_0001_s002"]
    assert chapters[1]["sentence_ids"] == ["chapter_0002_s001"]
    assert [item["sentence_id"] for item in atlas] == [
        "chapter_0001_s001",
        "chapter_0001_s002",
        "chapter_0002_s001",
    ]
    assert atlas[0]["text"] == "沈夜收到密信。"
    assert atlas[1]["text"] == "秦昭提醒他危险将近！"
    assert atlas[2]["text"] == "顾行舟已经提前布下埋伏？"


def test_parse_kv_line_reads_line_protocol_fields():
    payload = parse_kv_line(
        "EVENT|summary=沈夜拿到密信|characters=沈夜|organizations=白泽司|sentence_refs=chapter_0001_s001,chapter_0001_s002",
        record_type="EVENT",
        required_keys=("summary", "characters", "organizations", "sentence_refs"),
    )

    assert payload["summary"] == "沈夜拿到密信"
    assert payload["characters"] == "沈夜"
    assert payload["sentence_refs"] == "chapter_0001_s001,chapter_0001_s002"


def test_parse_sentence_ref_list_rejects_unknown_sentence_id():
    with pytest.raises(LineProtocolError, match="未知 sentence_id"):
        parse_sentence_ref_list(
            "chapter_0001_s001,chapter_0009_s003",
            valid_sentence_ids={"chapter_0001_s001", "chapter_0001_s002"},
        )
