from src.utils.common import read_file


def test_read_file_uses_utf8(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("hello", encoding="utf-8")
    assert read_file(str(path)) == "hello"
