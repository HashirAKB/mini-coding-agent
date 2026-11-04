from datetime import date

from dates import days_between


def test_three_days():
    assert days_between(date(2024, 1, 1), date(2024, 1, 3)) == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]
