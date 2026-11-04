from textutil import truncate


def test_never_longer_than_limit():
    for limit in range(3, 20):
        assert len(truncate("x" * 50, limit)) <= limit


def test_exact_fit_is_unchanged():
    assert truncate("abcdef", 6) == "abcdef"


def test_one_over():
    assert truncate("abcdefg", 6) == "abc..."
