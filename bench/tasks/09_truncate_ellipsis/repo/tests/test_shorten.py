from textutil import truncate


def test_shortened_text_fits():
    assert truncate("hello world", 8) == "hello..."
