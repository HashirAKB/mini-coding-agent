from numerals import to_roman


def test_four():
    assert to_roman(4) == "IV"


def test_1994():
    assert to_roman(1994) == "MCMXCIV"
