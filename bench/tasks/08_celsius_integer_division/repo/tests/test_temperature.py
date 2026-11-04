import pytest

from units import to_fahrenheit


def test_body_temperature():
    assert to_fahrenheit(37) == pytest.approx(98.6)
