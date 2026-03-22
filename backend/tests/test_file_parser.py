from pathlib import Path

from app.utils.file_parser import FileParser


def test_extract_txt_accepts_utf8_with_truncated_tail(tmp_path):
    expected = "这是浏览器上传测试内容。\n" * 4
    file_path = tmp_path / "truncated_utf8.txt"
    file_path.write_bytes(expected.encode("utf-8") + b"\xe8")

    result = FileParser.extract_text(str(file_path))

    assert result == expected


def test_extract_txt_detects_gb18030_content(tmp_path):
    expected = (
        "这是一个中文 GB18030 编码测试。\n"
        "江宁城外，苏檀儿与宁毅对账。\n"
        "乌启豪与席掌柜在账房里争执不下。\n"
    )
    file_path = tmp_path / "gb18030_novel.txt"
    file_path.write_bytes(expected.encode("gb18030"))

    result = FileParser.extract_text(str(file_path))

    assert result == expected
