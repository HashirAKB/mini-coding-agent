from searching import find


def test_single_element():
    assert find([4], 4) == 0


def test_every_position():
    items = [2, 4, 6, 8, 10]
    assert [find(items, x) for x in items] == [0, 1, 2, 3, 4]


def test_absent_and_empty():
    assert find([1, 2, 3], 5) == -1
    assert find([], 1) == -1
