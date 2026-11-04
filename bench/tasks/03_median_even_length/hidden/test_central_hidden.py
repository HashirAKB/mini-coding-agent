from numstats import median


def test_two_values_unsorted():
    assert median([5, 1]) == 3.0


def test_even_unsorted():
    assert median([10, 2, 4, 8]) == 6.0


def test_single_value():
    assert median([7]) == 7
