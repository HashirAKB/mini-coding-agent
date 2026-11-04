from datetime import date

from dates import days_between


def test_same_day():
    assert days_between(date(2024, 5, 5), date(2024, 5, 5)) == [date(2024, 5, 5)]


def test_month_boundary():
    days = days_between(date(2024, 1, 30), date(2024, 2, 2))
    assert len(days) == 4 and days[-1] == date(2024, 2, 2)
