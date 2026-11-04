from csvlite import parse_line


def test_escaped_quotes():
    assert parse_line('"say ""hi""",x') == ['say "hi"', "x"]


def test_empty_fields():
    assert parse_line("a,,b") == ["a", "", "b"]


def test_quoted_without_comma():
    assert parse_line('"plain"') == ["plain"]
