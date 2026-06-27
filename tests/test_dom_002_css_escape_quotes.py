from src.utils.dom import css_escape


def test_css_escape_escapes_quotes():
    assert css_escape('a"b') == 'a\\"b'
