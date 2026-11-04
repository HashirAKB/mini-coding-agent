from series import moving_average


def test_window_equal_to_length():
    assert moving_average([2, 4, 6], 3) == [4.0]


def test_window_longer_than_data():
    assert moving_average([1, 2], 3) == []


def test_window_of_one_is_identity():
    assert moving_average([5, 7], 1) == [5.0, 7.0]
