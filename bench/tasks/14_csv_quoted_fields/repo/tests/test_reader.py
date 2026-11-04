from csvlite import parse_line


def test_quoted_comma():
    assert parse_line('a,"b,c",d') == ["a", "b,c", "d"]
