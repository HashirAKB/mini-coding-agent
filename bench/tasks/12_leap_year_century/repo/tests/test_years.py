from calendar_utils import is_leap_year


def test_1900_is_not_leap():
    assert not is_leap_year(1900)


def test_2000_is_leap():
    assert is_leap_year(2000)
