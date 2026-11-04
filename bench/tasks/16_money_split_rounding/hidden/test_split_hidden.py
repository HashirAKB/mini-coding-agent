import pytest

from billing import split_bill


def test_shares_add_up():
    assert sum(split_bill(100, 7)) == pytest.approx(100.00)


def test_tiny_amount():
    assert split_bill(0.05, 2) == [0.03, 0.02]


def test_even_split():
    assert split_bill(9, 3) == [3.0, 3.0, 3.0]
