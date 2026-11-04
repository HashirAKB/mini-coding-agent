import pytest

from billing import split_bill


def test_ten_between_three():
    shares = split_bill(10.00, 3)
    assert shares == [3.34, 3.33, 3.33]
    assert sum(shares) == pytest.approx(10.00)
