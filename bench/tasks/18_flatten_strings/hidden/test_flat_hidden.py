from nested import flatten


def test_single_string():
    assert flatten(["x"]) == ["x"]


def test_tuples_and_bytes():
    assert flatten([(1, 2), [b"hi", ("z",)]]) == [1, 2, b"hi", "z"]


def test_empty():
    assert flatten([]) == []
