from numerals import to_roman


def test_forty_and_ninety():
    assert to_roman(40) == "XL"
    assert to_roman(90) == "XC"


def test_largest():
    assert to_roman(3999) == "MMMCMXCIX"


def test_additive_still_works():
    assert to_roman(8) == "VIII"
