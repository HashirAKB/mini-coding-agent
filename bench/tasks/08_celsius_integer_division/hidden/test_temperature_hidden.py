import pytest

from units import to_fahrenheit


def test_fractional_input():
    assert to_fahrenheit(36.6) == pytest.approx(97.88)


def test_one_degree():
    assert to_fahrenheit(1) == pytest.approx(33.8)


def test_minus_forty():
    assert to_fahrenheit(-40) == pytest.approx(-40)
