from nested import flatten


def test_strings_are_kept_whole():
    assert flatten([1, [2, [3, "ab"]]]) == [1, 2, 3, "ab"]
