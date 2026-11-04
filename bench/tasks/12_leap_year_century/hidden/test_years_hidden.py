from calendar_utils import is_leap_year


def test_more_centuries():
    assert not is_leap_year(2100)
    assert is_leap_year(2400)


def test_ordinary_years():
    assert is_leap_year(2024)
    assert not is_leap_year(2023)
